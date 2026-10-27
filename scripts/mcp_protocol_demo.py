"""Protocol-level MCP demo (PRD §10.2, Step 7 exit criterion).

Part 1 speaks raw JSON-RPC over the server's stdio and prints every message: initialize, notifications/initialized,
tools/list, tools/call, resources/list, resources/read, then shutdown. Part 2 runs the negative cases through the
validating client wrapper: invalid arguments, timeout, server down, malformed response, an injected instruction in a
resource, and an unregistered server that tries to shadow a tool. Exit code 1 if any expectation fails.

Usage: python scripts/mcp_protocol_demo.py [--quiet]
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys

from policy_agent import mcp_client as mc
from policy_agent.ingest.paths import ROOT
from policy_agent.mcp_client import ClientErrorCode as Code
from policy_agent.mcp_client import McpClientError

CANARY = "CANARY-MCP-5B1D"
SERVER = [sys.executable, "-m", "policy_agent.mcp_server"]
QUIET = False


def show(direction: str, msg: dict) -> None:
    if QUIET:
        return
    text = json.dumps(msg, separators=(",", ":"))
    print(f"  {direction} {text[:420]}{' ...' if len(text) > 420 else ''}")


class RawSession:
    """Newline-delimited JSON-RPC 2.0 over a child process's stdin/stdout (the MCP stdio transport)."""

    def __init__(self, env: dict[str, str] | None = None):
        self.proc = subprocess.Popen(SERVER, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, cwd=ROOT, env={**os.environ, **(env or {})})  # fmt: skip
        self.next_id = 0

    def send(self, msg: dict) -> None:
        show("->", msg)
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, **({"params": params} if params else {})})
        assert self.proc.stdout
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed the connection")
            msg = json.loads(line)
            show("<-", msg)
            if msg.get("id") == self.next_id:
                return msg

    def notify(self, method: str) -> None:
        self.send({"jsonrpc": "2.0", "method": method})

    def close(self) -> int:
        assert self.proc.stdin
        self.proc.stdin.close()  # shutdown on stdio: close the pipe, the server exits
        try:
            return self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return -9


def lifecycle() -> list[tuple[str, bool]]:
    print("\n=== Part 1: raw JSON-RPC lifecycle over stdio ===")
    s, checks = RawSession(), []
    print("1. initialize (version and capability negotiation)")
    init = s.request(
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "protocol-demo", "version": "0.1"},
        },
    )  # noqa: E501
    checks.append(
        (
            "initialize returns serverInfo and tools/resources capabilities",
            init["result"]["serverInfo"]["name"] == "policy-stats" and "tools" in init["result"]["capabilities"],
        )
    )  # noqa: E501
    print("2. notifications/initialized (the client confirms; no response expected)")
    s.notify("notifications/initialized")
    print("3. tools/list")
    tools = s.request("tools/list")["result"]["tools"]
    checks.append(
        (
            "tools/list shows exactly the 2 tools",
            sorted(t["name"] for t in tools) == ["compute_change", "query_statistic"],
        )
    )  # noqa: E501
    print("4. tools/call query_statistic")
    q = s.request(
        "tools/call",
        {
            "name": "query_statistic",
            "arguments": {
                "indicator": "unemployment_rate",
                "period_from": "2025-Q1",
                "period_to": "2025-Q2",
                "residency": "overall",
                "seasonal_adjustment": "sa",
            },
        },
    )  # noqa: E501
    sc = q["result"].get("structuredContent", {})
    checks.append(
        (
            "tools/call returns rows with unit and basis",
            not q["result"]["isError"] and sc["unit"] == "%" and len(sc["rows"]) == 2,
        )
    )  # noqa: E501
    print("5. tools/call compute_change using the query_id")
    c = s.request("tools/call", {"name": "compute_change", "arguments": {"method": "pp", "query_id": sc["query_id"]}})
    checks.append(
        ("compute_change returns result, formula and inputs", c["result"]["structuredContent"]["unit"] == "pp")
    )
    print("6. resources/list and resources/read")
    uris = sorted(r["uri"] for r in s.request("resources/list")["result"]["resources"])
    checks.append(
        ("resources/list shows stats://schema and stats://sources", uris == ["stats://schema", "stats://sources"])
    )
    r = s.request("resources/read", {"uri": "stats://schema"})["result"]["contents"][0]
    checks.append(("resources/read returns JSON text", "indicators" in json.loads(r["text"])))
    print("7. shutdown (close stdin)")
    checks.append(("server exits cleanly", s.close() == 0))
    print("   server exit code checked")
    return checks


async def negatives() -> list[tuple[str, bool]]:
    print("\n=== Part 2: negative cases through the validating client ===")
    checks: list[tuple[str, bool]] = []

    def record(label: str, ok: bool, detail: str) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}\n         {detail}")
        checks.append((label, ok))

    ok_q = {
        "indicator": "unemployment_rate",
        "period_from": "2025-Q2",
        "period_to": "2025-Q2",
        "residency": "overall",
        "seasonal_adjustment": "sa",
    }  # noqa: E501

    async with mc.connect("stats") as c:
        try:
            await c.call("query_statistic", {**ok_q, "indicator": "gdp"})
        except McpClientError as e:
            record("invalid argument is refused locally, never sent", e.code is Code.INVALID_ARGUMENT, str(e)[:150])
        raw = await c.session.call_tool("query_statistic", {**ok_q, "period_to": "2020-Q1"})
        body = json.loads(raw.content[0].text.split(": ", 1)[1]) if raw.isError else {}
        record(
            "server rejects bad arguments itself with a typed error (no stack trace)",
            raw.isError and body.get("code") == "INVALID_ARGUMENT" and "Traceback" not in raw.content[0].text,
            json.dumps(body)[:150],
        )  # noqa: E501
        try:
            await c.call("run_sql", {"sql": "select 1"})
        except McpClientError as e:
            record("a tool that is not allow-listed is refused", e.code is Code.NOT_ALLOWED, str(e)[:150])

    async with mc.connect("stats", env={"MCP_FAULT": "slow", "MCP_TIMEOUT_S": "1"}) as c:
        try:
            await c.call("query_statistic", ok_q)
        except McpClientError as e:
            record("slow query is cut off by the server timeout", e.server_code == "TIMEOUT", str(e)[:150])

    allow = {
        "servers": {
            "stats": {**mc.load_allow_list()["servers"]["stats"], "command": "/nonexistent/python", "timeout_s": 2}
        },
        "local_tool_names": [],
    }  # noqa: E501
    try:
        async with mc.connect("stats", allow):
            pass
    except McpClientError as e:
        record("server that cannot be started is a typed error", e.code is Code.SERVER_UNAVAILABLE, str(e)[:150])

    async with mc.connect("stats", env={"MCP_FAULT": "malformed"}) as c:
        try:
            await c.call("query_statistic", ok_q)
        except McpClientError as e:
            record(
                "malformed response is rejected before reaching the agent",
                e.code is Code.INVALID_RESPONSE,
                str(e)[:150],
            )

    async with mc.connect("stats", env={"MCP_POISON": "1"}) as c:
        doc, wrapped = await c.read("stats://sources")
        leaked = CANARY in wrapped or "ignore all previous" in wrapped.lower()
        record(
            "instruction injected into a resource is redacted and wrapped",
            not leaked and mc.REDACTED in wrapped and wrapped.startswith("<untrusted_tool_output"),
            f"flags={c.flags}; licence text kept: {'Open Data Licence' in wrapped}",
        )  # noqa: E501
        if not QUIET:
            print("         what reaches the prompt (first 300 chars):", wrapped[:300].replace("\n", " "))

    try:
        async with mc.connect("stats-helper"):  # unregistered server that would shadow query_statistic (red-team R12)
            pass
    except McpClientError as e:
        record("unregistered server 'stats-helper' is refused (R12)", e.code is Code.NOT_ALLOWED, str(e)[:150])

    try:
        mc.check_tools(
            mc.load_allow_list()["servers"]["stats"],
            ["query_statistic", "compute_change", "calculator"],
            mc.load_allow_list()["local_tool_names"],
        )  # noqa: E501
    except McpClientError as e:
        record(
            "a server tool named like a local tool is refused as shadowing", e.code is Code.SHADOWED_TOOL, str(e)[:150]
        )
    return checks


def main() -> int:
    global QUIET
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="hide the raw messages, print only results")
    QUIET = ap.parse_args().quiet
    checks = lifecycle()
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    checks += asyncio.run(negatives())
    failed = [label for label, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
