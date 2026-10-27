"""The agent's tools. Local tools live here; the statistics tools come from the MCP server (see mcp_tools)."""

from policy_agent.tools.calculator import calculate, calculator_tool
from policy_agent.tools.format_report import SAFE_DIR, format_report_tool, render_markdown, report_path, write_report
from policy_agent.tools.search_corpus import SearchContext, make_search_corpus

LOCAL_TOOL_NAMES = [
    "search_corpus",
    "calculator",
    "format_report",
]  # must match local_tool_names in config/mcp_servers.yaml

__all__ = [
    "LOCAL_TOOL_NAMES", "SAFE_DIR", "SearchContext", "calculate", "calculator_tool", "format_report_tool", "make_search_corpus",
    "render_markdown", "report_path", "write_report",
]  # fmt: skip
