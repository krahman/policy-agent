"""Render an answer as a Markdown brief and (only after confirmation) save it under reports/ (PRD §9.4, §9.6).

Writes are restricted to one directory, the file name is derived from a hash of the answer (so saving twice is
idempotent), and the graph asks the user to confirm before anything touches the disk."""

import hashlib
import json
from pathlib import Path

from langchain_core.tools import tool

from policy_agent.ingest.paths import ROOT

SAFE_DIR = ROOT / "reports"
KIND_LABEL = {
    "source_fact": "Source fact",
    "statistical_finding": "Statistical finding",
    "model_inference": "Model inference",
}


def render_markdown(answer: dict, question: str = "") -> str:
    lines = ["# Policy research brief", ""]
    if question:
        lines += [f"**Question:** {question}", ""]
    lines += [
        f"**Status:** {answer['status']}  |  **Confidence:** {answer.get('confidence', 'medium')}",
        "",
        answer["summary"],
        "",
    ]
    for cl in answer.get("claims", []):
        lines.append(f"- **{KIND_LABEL.get(cl['kind'], cl['kind'])}:** {cl['text']}")
        for c in cl.get("citations", []):
            lines.append(f'  - source `{c["source_id"]}`, chunk `{c["chunk_id"]}`: "{c["quote"][:200]}"')
        if cl.get("tool_call_ids"):
            lines.append(f"  - computed by tool call(s): {', '.join(cl['tool_call_ids'])}")
    for n in answer.get("conflicts", []):
        lines += ["", f"**Conflict:** {n['description']}"]
    if answer.get("limitations"):
        lines += ["", "**Limitations:**"] + [f"- {x}" for x in answer["limitations"]]
    lines += [
        "",
        "_Model inferences and arithmetic are labelled; check the cited sources before relying on this brief._",
    ]
    return "\n".join(lines) + "\n"


def report_path(answer: dict) -> Path:
    digest = hashlib.sha256(json.dumps(answer, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return SAFE_DIR / f"brief-{digest}.md"


def write_report(path: Path, markdown: str) -> Path:
    """Write only inside reports/ (resolved, so '..' and symlinks cannot escape). Same answer, same file."""
    resolved = path.resolve()
    if resolved.parent != SAFE_DIR.resolve():
        raise PermissionError(f"refusing to write outside {SAFE_DIR.name}/")
    SAFE_DIR.mkdir(exist_ok=True)
    resolved.write_text(markdown)
    return resolved


@tool("format_report")
def format_report_tool(answer_json: str, question: str = "") -> str:
    """Render a validated answer (as JSON) into a Markdown brief and return the text. It never writes a file; saving
    needs the user's confirmation and happens in the agent's report step."""
    return render_markdown(json.loads(answer_json), question)
