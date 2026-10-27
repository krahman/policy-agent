"""Repository paths and the frozen scope window."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
SYNTHETIC = ROOT / "data" / "synthetic" / "memos"
PROCESSED = ROOT / "data" / "processed"
CORPUS = json.loads((ROOT / "config" / "corpus.json").read_text())

SCOPE_FROM: str = CORPUS["scope_window"]["from"]  # e.g. "2021-Q3"
SCOPE_TO: str = CORPUS["scope_window"]["to"]  # e.g. "2026-Q2"
