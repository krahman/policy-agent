"""Command-line interface: ask a question, see a labelled, cited answer (PRD §6, §16).

uv run python -m policy_agent.cli "What was the overall unemployment rate in 4Q 2023?" --verbose
uv run python -m policy_agent.cli "..." --role analyst_internal --save-report
uv run python -m policy_agent.cli "..." --fault mcp_timeout        # fault injection (see FAULTS)
"""

import argparse
import os
import sys
import textwrap

from dotenv import load_dotenv

from policy_agent.graph.runtime import FAULTS, AgentRuntime
from policy_agent.ingest.paths import ROOT

LABEL = {
    "source_fact": "SOURCE FACT        ",
    "statistical_finding": "STATISTICAL FINDING",
    "model_inference": "MODEL INFERENCE    ",
}


def render(o: dict, verbose: bool = False) -> str:
    a = o["answer"] or {}
    out = [f"[{o['status'].upper()}]  confidence: {a.get('confidence', '-')}  |  {o['latency_ms'] / 1000:.1f}s  |  "
           f"{o['agent']['llm_calls']} model calls  |  tools: {', '.join(o['agent']['tools']) or 'none'}", ""]  # fmt: skip
    out += textwrap.wrap(a.get("summary", ""), 100) or [""]
    if a.get("clarifying_question"):
        out += ["", "Question for you: " + a["clarifying_question"]]
    for cl in a.get("claims", []):
        out += ["", f"  {LABEL.get(cl['kind'], cl['kind'])}  {cl['text']}"]
        for c in cl.get("citations", []):
            out.append(f'      cites {c["source_id"]} / chunk {c["chunk_id"]}: "{c["quote"][:90]}"')
        for t in cl.get("tool_call_ids", []):
            out.append(f"      computed by tool call {t}")
    for n in a.get("conflicts", []):
        out += ["", "  CONFLICT  " + n["description"]] + [f"      {v}" for v in n.get("values", [])]
    if a.get("limitations"):
        out += ["", "Limitations:"] + [f"  - {x}" for x in a["limitations"]]
    if verbose:
        out += ["", "Trace:"] + [f"  {line}" for line in o["agent"]["log"]]
        out += [
            f"  stop reason: {o['agent']['stop_reason']}",
            f"  first-pass validation: {o['validation']['first_pass'] or 'clean'}",
        ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="policy_agent", description="Evidence-grounded Singapore labour-market research assistant"
    )
    ap.add_argument("question")
    ap.add_argument("--role", default="analyst_public", choices=["analyst_public", "analyst_internal"])
    ap.add_argument("--model", default="anthropic/claude-haiku-5.5")
    ap.add_argument("--verbose", "-v", action="store_true", help="print the node-by-node trace and validation results")
    ap.add_argument(
        "--save-report", action="store_true", help="render a Markdown brief and ask before saving it to reports/"
    )
    ap.add_argument(
        "--fault", action="append", default=[], choices=sorted(FAULTS), help="inject a failure (repeatable)"
    )
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")
    if "OPENROUTER_API_KEY" not in os.environ:
        print("OPENROUTER_API_KEY is not set (see .env.example)", file=sys.stderr)
        return 2
    with AgentRuntime(model=args.model, embedding="voyageai/voyage-4", faults=set(args.fault)) as rt:
        o = rt.ask(args.question, args.role, want_report=args.save_report)
        print(render(o, args.verbose))
        if args.save_report and o["agent"]["interrupted"]:
            reply = input("\nSave this brief to the reports folder? [y/N] ").strip().lower()
            rep = rt.confirm_report(o["agent"]["thread_id"], approve=reply == "y")
            print(f"Saved to {rep['path']}" if rep.get("saved") else "Not saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
