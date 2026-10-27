"""Load chunks and apply the permission filter *before* any ranking (PRD §7.3)."""

import json
import re
from functools import lru_cache

from policy_agent.ingest.paths import PROCESSED

# analyst_public may read public chunks only; analyst_internal may read both
ROLE_ACCESS = {"analyst_public": {"public"}, "analyst_internal": {"public", "internal"}}


@lru_cache(maxsize=1)
def load_chunks() -> tuple[dict, ...]:
    rows = [json.loads(line) for line in (PROCESSED / "chunks.jsonl").read_text().splitlines()]
    return tuple(sorted(rows, key=lambda c: c["chunk_id"]))  # fixed order => deterministic ties


def visible_chunks(role: str) -> list[dict]:
    if role not in ROLE_ACCESS:
        raise ValueError(f"unknown role {role!r}")
    allowed = ROLE_ACCESS[role]
    return [c for c in load_chunks() if c["access_level"] in allowed]


_NUM = re.compile(r"(?<=\d),(?=\d{3}\b)")
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumerics; thousands separators removed so '4,620' and '4620' match."""
    return _TOKEN.findall(_NUM.sub("", text.lower()))
