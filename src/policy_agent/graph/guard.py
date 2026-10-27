"""guard_input: cheap, deterministic checks before any model sees the question (PRD §9.3, §13.1).

This is the first of several layers, not the only one: the router, the synthesis prompt rules, the output validator and
the allow-lists catch what a regex misses."""

import re

RULES: list[tuple[str, re.Pattern]] = [
    (
        "injection",
        re.compile(
            r"ignore (all |any |the )?(previous|prior|above|your) (instructions|rules|guidelines)|disregard (your|the|all) (guidelines|instructions|rules)|pretend (you have|there are) no (rules|restrictions)|you have no (rules|restrictions)|forget (your|all) (instructions|rules)",
            re.I,
        ),
    ),  # noqa: E501
    (
        "prompt_leak",
        re.compile(
            r"(print|show|reveal|output|repeat|display|tell me)\b.{0,40}(system prompt|hidden instructions|your instructions|instructions you were given|initial prompt)",
            re.I,
        ),
    ),  # noqa: E501
    (
        "pii",
        re.compile(
            r"\bNRIC\b|\bFIN\b number|names? (and|or) (nric|address|phone)|list the names|home address|phone numbers? of",
            re.I,
        ),
    ),
    (
        "sql",
        re.compile(
            r"\b(drop|delete|truncate|alter|insert|update)\s+(table|from|into)\b|;\s*select\b|run (this|the) (sql|query)|\bselect\b.+\bfrom\b",
            re.I,
        ),
    ),  # noqa: E501
    (
        "file_write",
        re.compile(r"(save|write|store|export)\b.{0,50}(/etc|/usr|/var|/bin|~/|\.\./|C:\\|/root|cron)", re.I),
    ),
    (
        "mcp_load",
        re.compile(
            r"load (an? )?(unregistered|unknown|new|external)\b.{0,40}\bmcp\b|add (an? )?mcp server|connect to (an? )?(other|new) mcp",
            re.I,
        ),
    ),  # noqa: E501
]
REFUSAL = {
    "injection": "I can't change or ignore my rules. I can answer questions about Singapore labour statistics.",
    "prompt_leak": "I can't share my instructions. I can answer questions about Singapore labour statistics.",
    "pii": "I can't provide individuals' personal records (names, NRIC numbers or addresses). I can share published aggregate statistics.",  # noqa: E501
    "sql": "I can't run SQL or modify the statistics store. The statistics tools take typed parameters only; ask in plain words.",
    "file_write": "I can only save briefs inside the reports folder, and only after you confirm. I can't write to that location.",
    "mcp_load": "I can only use the MCP servers on the approved list. I can't load another one.",
}


def check(question: str) -> str | None:
    """Name of the first rule the question trips, or None."""
    for name, pat in RULES:
        if pat.search(question):
            return name
    return None
