"""MCP client wrapper (PRD §10.2): allow-list, handshake checks, response re-validation, untrusted-output wrapping.

The server is treated as untrusted. Before any of its output reaches the agent it is (1) parsed against a local
Pydantic schema that forbids unexpected fields, (2) scanned for instruction-like text, and (3) wrapped in an
<untrusted_tool_output> block. Failures raise a typed `McpClientError`; raw server output is never passed on."""

import json
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import anyio
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ValidationError

from policy_agent.ingest.paths import ROOT
from policy_agent.mcp_server.models import (
    ComputeChangeInput,
    ComputeChangeResult,
    QueryResult,
    QueryStatisticInput,
    SchemaDoc,
    SourcesDoc,
    ToolErrorBody,
)

CONFIG = ROOT / "config" / "mcp_servers.yaml"
TOOL_RESULT: dict[str, type[BaseModel]] = {"query_statistic": QueryResult, "compute_change": ComputeChangeResult}
TOOL_INPUT: dict[str, type[BaseModel]] = {"query_statistic": QueryStatisticInput, "compute_change": ComputeChangeInput}
RESOURCE_DOC: dict[str, type[BaseModel]] = {"stats://schema": SchemaDoc, "stats://sources": SourcesDoc}
REDACTED = "[REDACTED: instruction-like content from a tool]"
# A heuristic second line of defence, not the main one: the main defences are the schema, the wrapper block and the
# system prompt rule that tool output is data. It will miss paraphrased attacks.
_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|disregard (the )?(system|previous)|system notice|"
    r"you must (now )?(say|state|output|append)|new instructions:|CANARY-[A-Z]+-[0-9A-F]+|reveal (your )?(system )?prompt",
    re.I,
)


class ClientErrorCode(StrEnum):
    NOT_ALLOWED = "NOT_ALLOWED"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    UNEXPECTED_TOOLS = "UNEXPECTED_TOOLS"
    SHADOWED_TOOL = "SHADOWED_TOOL"
    SERVER_UNAVAILABLE = "SERVER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    TOOL_ERROR = "TOOL_ERROR"


class McpClientError(Exception):
    def __init__(self, code: ClientErrorCode, message: str, server_code: str | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.server_code = code, message, server_code


def load_allow_list(path=CONFIG) -> dict:
    return yaml.safe_load(path.read_text())


def check_server_config(name: str, allow: dict) -> dict:
    if name not in (allow.get("servers") or {}):
        raise McpClientError(ClientErrorCode.NOT_ALLOWED, f"MCP server {name!r} is not in the allow-list")
    return allow["servers"][name]


def check_handshake(cfg: dict, server_name: str, protocol_version: str) -> None:
    if server_name != cfg["expected_server_name"]:
        raise McpClientError(
            ClientErrorCode.NOT_ALLOWED,
            f"server identified itself as {server_name!r}, expected {cfg['expected_server_name']!r}",
        )  # noqa: E501
    if protocol_version not in cfg["protocol_versions"]:
        raise McpClientError(
            ClientErrorCode.VERSION_MISMATCH, f"protocol version {protocol_version!r} not in {cfg['protocol_versions']}"
        )  # noqa: E501


def check_tools(cfg: dict, names: list[str], local_names: list[str], taken: set[str] | None = None) -> None:
    got, want = set(names), set(cfg["expected_tools"])
    shadow = got & (set(local_names) | (taken or set()))
    if shadow:
        raise McpClientError(ClientErrorCode.SHADOWED_TOOL, f"server tools shadow existing tools: {sorted(shadow)}")
    if got != want:
        raise McpClientError(
            ClientErrorCode.UNEXPECTED_TOOLS, f"unexpected {sorted(got - want)}, missing {sorted(want - got)}"
        )  # noqa: E501


def sanitise(obj: Any, flags: list[str], path: str = "") -> Any:
    """Replace instruction-like strings anywhere in a parsed payload; record where."""
    if isinstance(obj, str):
        if _INJECTION.search(obj):
            flags.append(path or "$")
            return REDACTED
        return obj
    if isinstance(obj, list):
        return [sanitise(x, flags, f"{path}[{i}]") for i, x in enumerate(obj)]
    if isinstance(obj, dict):
        return {k: sanitise(v, flags, f"{path}.{k}" if path else k) for k, v in obj.items()}
    return obj


def wrap(source: str, payload: Any, flags: list[str] | None = None) -> str:
    """The only form in which MCP output may enter a prompt. The close tag is stripped from the payload."""
    body = json.dumps(payload, indent=1, default=str).replace("</untrusted_tool_output>", "")
    note = f' flagged="{",".join(flags)}"' if flags else ""
    return f'<untrusted_tool_output source="{source}"{note}>\n{body}\n</untrusted_tool_output>'


def parse_result(tool: str, result: CallToolResult) -> BaseModel:
    """Turn a raw CallToolResult into a validated model, or raise a typed error. Nothing raw escapes."""
    text = next((c.text for c in result.content if isinstance(c, TextContent)), "")
    if result.isError:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            body = ToolErrorBody.model_validate_json(m.group(0)) if m else None
        except ValidationError:
            body = None
        if body is None:
            raise McpClientError(ClientErrorCode.TOOL_ERROR, "the server reported an error in an unrecognised format")
        raise McpClientError(ClientErrorCode.TOOL_ERROR, body.message, server_code=body.code.value)
    schema = TOOL_RESULT.get(tool)
    if schema is None:
        raise McpClientError(ClientErrorCode.UNEXPECTED_TOOLS, f"no schema for tool {tool!r}")
    payload = result.structuredContent
    if payload is None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise McpClientError(ClientErrorCode.INVALID_RESPONSE, "tool output is not JSON") from e
    try:
        return schema.model_validate(payload)
    except ValidationError as e:
        fields = sorted({".".join(map(str, x["loc"])) for x in e.errors()})
        raise McpClientError(
            ClientErrorCode.INVALID_RESPONSE, f"tool output failed schema validation at {fields}"
        ) from e


@dataclass
class StatsConnection:
    name: str
    cfg: dict
    session: ClientSession
    protocol_version: str
    flags: list[str] = field(default_factory=list)  # paths of anything redacted so far, for the audit trail

    def _clean(self, model: BaseModel) -> tuple[Any, list[str]]:
        flags: list[str] = []
        payload = sanitise(model.model_dump(mode="json"), flags)
        self.flags += flags
        return payload, flags

    async def call(self, tool: str, arguments: dict) -> tuple[BaseModel, str]:
        """Validate arguments locally, call, re-validate the response. Returns (model, wrapped_text_for_the_prompt)."""
        schema = TOOL_INPUT.get(tool)
        if schema is None or tool not in self.cfg["expected_tools"]:
            raise McpClientError(ClientErrorCode.NOT_ALLOWED, f"tool {tool!r} is not allow-listed")
        try:
            schema.model_validate(arguments)
        except ValidationError as e:
            raise McpClientError(
                ClientErrorCode.INVALID_ARGUMENT,
                "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()),
            ) from e  # noqa: E501
        try:
            with anyio.fail_after(self.cfg["timeout_s"]):
                raw = await self.session.call_tool(tool, arguments)
        except TimeoutError as e:
            raise McpClientError(ClientErrorCode.TIMEOUT, f"no response within {self.cfg['timeout_s']} s") from e
        except (anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream, ConnectionError) as e:
            raise McpClientError(ClientErrorCode.SERVER_UNAVAILABLE, "the MCP server closed the connection") from e
        model = parse_result(tool, raw)
        payload, flags = self._clean(model)
        return model, wrap(f"{self.name}.{tool}", payload, flags)

    async def read(self, uri: str) -> tuple[BaseModel, str]:
        if uri not in self.cfg["expected_resources"]:
            raise McpClientError(ClientErrorCode.NOT_ALLOWED, f"resource {uri!r} is not allow-listed")
        try:
            with anyio.fail_after(self.cfg["timeout_s"]):
                res = await self.session.read_resource(uri)  # type: ignore[arg-type]
        except TimeoutError as e:
            raise McpClientError(ClientErrorCode.TIMEOUT, "resource read timed out") from e
        text = next((getattr(c, "text", "") for c in res.contents), "")
        try:
            doc = RESOURCE_DOC[uri].model_validate_json(text)
        except ValidationError as e:
            fields = sorted({".".join(map(str, x["loc"])) for x in e.errors()})
            raise McpClientError(
                ClientErrorCode.INVALID_RESPONSE, f"resource {uri} failed schema validation at {fields}"
            ) from e  # noqa: E501
        payload, flags = self._clean(doc)
        return doc, wrap(f"{self.name}:{uri}", payload, flags)

    async def langchain_tools(self) -> list:
        """The server's tools as LangChain tools (langchain-mcp-adapters), with every result passed through the
        same validation and wrapping as `call`, via a tool interceptor."""
        from langchain_mcp_adapters.tools import load_mcp_tools

        async def interceptor(request, handler):
            raw = await handler(request)
            model = parse_result(request.name, raw)
            payload, flags = self._clean(model)
            return CallToolResult(
                content=[TextContent(type="text", text=wrap(f"{self.name}.{request.name}", payload, flags))],
                isError=False,
            )  # noqa: E501

        return await load_mcp_tools(self.session, server_name=self.name, tool_interceptors=[interceptor])


@asynccontextmanager
async def connect(name: str = "stats", allow: dict | None = None, env: dict[str, str] | None = None):
    """Start an allow-listed server over stdio, verify it, and yield a `StatsConnection`."""
    allow = allow or load_allow_list()
    cfg = check_server_config(name, allow)  # refuse before anything is started
    params = StdioServerParameters(
        command=cfg["command"].replace("{python}", sys.executable), args=cfg["args"],
        env={**(cfg.get("env") or {}), **(env or {})}, cwd=str(ROOT),
    )  # fmt: skip
    try:
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            try:
                with anyio.fail_after(cfg["timeout_s"]):
                    init = await session.initialize()
                    check_handshake(cfg, init.serverInfo.name, str(init.protocolVersion))
                    tools = await session.list_tools()
            except TimeoutError as e:
                raise McpClientError(ClientErrorCode.TIMEOUT, "server did not complete the handshake") from e
            check_tools(cfg, [t.name for t in tools.tools], allow.get("local_tool_names", []))
            yield StatsConnection(name, cfg, session, str(init.protocolVersion))
    except McpClientError:
        raise
    except ExceptionGroup as e:
        # the SDK reports failures in its task groups as groups: surface our own errors (or any programming error)
        # unchanged, and call it SERVER_UNAVAILABLE only when every cause is a transport problem
        inner = list(e.exceptions)
        while inner and isinstance(inner[0], ExceptionGroup):
            inner = list(inner[0].exceptions)
        mine = next((x for x in inner if isinstance(x, McpClientError)), None)
        if mine:
            raise mine from e
        if all(
            isinstance(x, OSError | anyio.ClosedResourceError | anyio.BrokenResourceError | anyio.EndOfStream)
            for x in inner
        ):
            raise McpClientError(ClientErrorCode.SERVER_UNAVAILABLE, "could not start or talk to the server") from e
        raise inner[0] from e
    except OSError as e:
        raise McpClientError(
            ClientErrorCode.SERVER_UNAVAILABLE, f"could not start or talk to the server: {type(e).__name__}"
        ) from e
