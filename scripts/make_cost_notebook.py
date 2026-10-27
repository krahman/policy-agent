"""Build and execute notebooks/09_cost_latency.ipynb: cost and latency of every system, from saved results.
Run: uv run python scripts/make_cost_notebook.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _notebook import build, code, md  # noqa: E402

cells = [
    md("""# 09 · Cost and latency

What each system costs per question and how long it takes, from the saved results (no model calls). Costs are the model tokens priced from `config/pricing.yaml`
(OpenRouter's published rates) plus the re-ranker's per-search fee. Targets set before measuring: p50 8 s, p95 20 s."""),
    code("""import json

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display

from policy_agent.ingest.paths import ROOT

R = ROOT / "eval" / "results"
pd.set_option("display.width", 170)
systems = {
    "B0 BM25 only (no LLM)": "B0_dev",
    "E6 chain, Haiku": "E6_dev",
    "E5 chain, Sonnet": "E5_dev",
    "E7 router agent": "E7_dev",
    "E8 final agent": "E8_dev",
    "E6T chain (held-out)": "E6T_test",
    "E7T router agent (held-out)": "E7T_test",
    "E8T final agent (held-out)": "E8T_test",
}
rows = {}
for name, f in systems.items():
    d = json.loads((R / f"{f}.json").read_text())
    rows[name] = {
        "runs": d["n_runs"],
        "cost per run $": d["cost_usd"]["mean_per_run"],
        "p50 s": d["latency_ms"]["p50"] / 1000,
        "p95 s": d["latency_ms"]["p95"] / 1000,
    }
table = pd.DataFrame(rows).T
display(table.round({"cost per run $": 4, "p50 s": 1, "p95 s": 1}))"""),
    code("""fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
t = table.drop("E5 chain, Sonnet")
ax[0].barh(t.index, t["p50 s"], color="#4C78A8", label="p50")
ax[0].barh(t.index, t["p95 s"] - t["p50 s"], left=t["p50 s"], color="#9ecae9", label="to p95")
ax[0].axvline(8, color="#E45756", linestyle="--", lw=1)
ax[0].axvline(20, color="#E45756", linestyle=":", lw=1)
ax[0].invert_yaxis()
ax[0].set_xlabel("seconds (dashed: p50 target 8 s; dotted: p95 target 20 s)")
ax[0].legend(fontsize=8)
ax[1].barh(table.index, table["cost per run $"] * 1000, color="#F58518")
ax[1].invert_yaxis()
ax[1].set_xlabel("thousandths of a dollar per question")
ax[1].set_yticklabels([])
plt.tight_layout()
plt.show()
sonnet, haiku = table.loc["E5 chain, Sonnet", "cost per run $"], table.loc["E6 chain, Haiku", "cost per run $"]
print(f"Sonnet costs {sonnet / haiku:.0f} times Haiku per question (E5 is omitted from the latency chart; it is in the table above).")"""),
    md(
        "## Where the time goes\nThe agent makes two or three sequential model calls (choose tools, maybe a second round, write the answer), and the dense query embedding and re-ranker are network calls. Per-tool timings are in each run's log."
    ),
    code("""d = json.loads((R / "E8T_test.json").read_text())
tool_ms = {}
for r in d["runs"]:
    for line in r["output"]["agent"]["log"]:
        if line.startswith("act:"):
            for tool, ms in __import__("re").findall(r"(\\w+)\\[ok,(\\d+)ms\\]", line):
                tool_ms.setdefault(tool, []).append(int(ms))
display(pd.DataFrame({k: pd.Series(v).describe()[["count", "50%", "max"]] for k, v in tool_ms.items()}).T.rename(columns={"50%": "median ms", "max": "max ms"}))
runs = pd.DataFrame([{"calls": r["output"]["agent"]["llm_calls"], "s": r["latency_ms"] / 1000} for r in d["runs"]])
display(runs.groupby("calls").s.agg(["count", "median", "max"]).round(1).rename(columns={"count": "runs", "median": "median s", "max": "max s"}))
print("A run with 3 model calls costs about one more model round trip than a run with 2; the tools themselves are fast (milliseconds) apart from an occasional slow search (up to a few seconds, when it must embed the question and re-rank).")"""),
    md("""## Reading this

- The final agent is **cheaper and faster than the router agent**, which paid for a model call just to route (p95 about 27 s down to 24 s held-out, 30 s to 18 s on dev).
- A plain chain is quicker at the median but fails more cases that need tools; both are far cheaper than Sonnet.
- Neither agent meets the 8 s / 20 s latency targets. The levers in `docs/INNOVATION.md` are to run independent searches in parallel and to use a single `act` round for plain lookups."""),
]

build("09_cost_latency.ipynb", cells)
