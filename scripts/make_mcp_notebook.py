"""Build and execute notebooks/05_mcp_demo.ipynb: capability discovery against the real server (PRD §10.2).
Run: uv run python scripts/make_mcp_notebook.py"""

from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# 05 · MCP server: capability discovery and use

The statistics store is exposed through an MCP server (`src/policy_agent/mcp_server/`). This notebook starts it over
stdio through the validating client (`policy_agent.mcp_client`) and walks through what a host discovers and can call.
The raw JSON-RPC lifecycle and the failure cases are in `scripts/mcp_protocol_demo.py`."""),
    code("""from policy_agent import mcp_client as mc

allow = mc.load_allow_list()
print("allow-listed servers:", list(allow["servers"]))
print("expected tools:", allow["servers"]["stats"]["expected_tools"])"""),
    md(
        "## 1. Connect: handshake and checks\nThe client refuses a server that is not allow-listed, speaks an unexpected protocol version, "
        "or exposes tools other than the expected two (or tools that shadow local ones)."
    ),
    code("""async def discover():
    async with mc.connect("stats") as c:
        tools = (await c.session.list_tools()).tools
        resources = (await c.session.list_resources()).resources
        prompts = (await c.session.list_prompts()).prompts
        return c.protocol_version, tools, resources, prompts

version, tools, resources, prompts = await discover()
print("negotiated protocol version:", version)
for t in tools:
    print(f"\\nTOOL {t.name}\\n  {t.description[:160]}...")
    for k, v in t.inputSchema["properties"].items():
        enum = v.get("enum")
        print(f"    {k:20} {v.get('description', '')[:70]}" + (f"  enum={enum[:4]}..." if enum else ""))
print("\\nRESOURCES:", [str(r.uri) for r in resources])
print("PROMPTS:", [p.name for p in prompts])"""),
    md(
        "## 2. Use a tool, then compute on its result\n`query_statistic` returns the rows plus the unit, residency, seasonal-adjustment basis, source and "
        "release date, and a `query_id`. `compute_change` takes that id, so the arithmetic is done by code and shows its formula."
    ),
    code("""async def demo():
    async with mc.connect("stats") as c:
        q, wrapped = await c.call("query_statistic", {"indicator": "unemployment_rate", "period_from": "2025-Q1", "period_to": "2026-Q2",
                                                      "residency": "overall", "seasonal_adjustment": "sa"})
        ch, _ = await c.call("compute_change", {"method": "pp", "query_id": q.query_id})
        return q, ch, wrapped

q, ch, wrapped = await demo()
print(f"{q.unit} | residency={q.residency} | basis={q.seasonal_adjustment} | {q.source_id} | released {q.release_date}")
for r in q.rows:
    print(f"  {r.period}: {r.value}")
print("\\nchange:", ch.result, ch.unit, "| formula:", ch.formula, "| inputs:", ch.inputs)
print("\\nwhat the agent's prompt would contain:\\n", wrapped[:420])"""),
    md(
        "## 3. The server refuses to guess\nLeaving out the residency returns every residency and basis, with a warning, instead of picking one."
    ),
    code("""async def ambiguous():
    async with mc.connect("stats") as c:
        q, _ = await c.call("query_statistic", {"indicator": "unemployment_rate", "period_from": "2025-Q2", "period_to": "2025-Q2"})
        return q

q = await ambiguous()
print("residency:", q.residency, "| basis:", q.seasonal_adjustment, "| rows:", len(q.rows))
for w in q.warnings:
    print("WARNING:", w)"""),
    md("## 4. Resources\n`stats://schema` says what exists; `stats://sources` carries provenance and licence."),
    code("""async def resources_demo():
    async with mc.connect("stats") as c:
        schema, _ = await c.read("stats://schema")
        sources, _ = await c.read("stats://sources")
        return schema, sources

schema, sources = await resources_demo()
print("scope window:", schema.scope_window)
for i in schema.indicators[:4]:
    print(" ", i)
print("\\n", len(sources.sources), "sources; licence of the first:", sources.sources[0].licence)"""),
]
nb = nbf.v4.new_notebook(
    cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}}
)
ExecutePreprocessor(timeout=300, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).preprocess(
    nb, {"metadata": {"path": str(ROOT)}}
)
out = ROOT / "notebooks" / "05_mcp_demo.ipynb"
nbf.write(nb, out)
print("wrote", out.relative_to(ROOT))
