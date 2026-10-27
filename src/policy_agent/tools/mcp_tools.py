"""MCP-backed statistics tools for the agent, loaded through the validating client (PRD §9.4, §10.2)."""

import json
import re

from policy_agent.ingest.paths import PROCESSED
from policy_agent.ingest.stat_cards import card_id
from policy_agent.mcp_client import StatsConnection

_BLOCK = re.compile(r"<untrusted_tool_output[^>]*>\n(.*)\n</untrusted_tool_output>", re.S)


async def load_stats_tools(conn: StatsConnection) -> list:
    """query_statistic and compute_change as LangChain tools; every result is validated and wrapped by the client."""
    return await conn.langchain_tools()


def unwrap(text: str) -> dict | None:
    """The JSON payload inside an <untrusted_tool_output> block, or None. The wrapper is ours, so this is safe to parse."""
    m = _BLOCK.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def stat_card_ids(rows: list[dict]) -> list[str]:
    """chunk_id of the stat card that renders each returned row, so tool results can be cited like any other chunk."""
    import pandas as pd

    out = []
    for r in rows:
        series = pd.Series({"source_id": r["source_id"], "residency": r.get("residency"), "age_group": r.get("age_group"),
                            "industry": r.get("industry"), "sex": None, "qualification": None,
                            "seasonal_adjustment": r["seasonal_adjustment"], "period": r["period"]})  # fmt: skip
        out.append(card_id(series))
    return out


__all__ = ["PROCESSED", "load_stats_tools", "stat_card_ids", "unwrap"]
