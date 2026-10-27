"""Write config/pricing.yaml from OpenRouter's public model catalogues (rates, date and source recorded).

Usage: python scripts/fetch_pricing.py anthropic/claude-haiku-5.5 ... --embeddings openai/text-embedding-3-small ...
"""

import argparse
import json
import urllib.request
from datetime import UTC, datetime

import yaml

from policy_agent.ingest.paths import ROOT

UA = {"User-Agent": "policy-agent-data-fetch/0.1 (research prototype; public data only)"}


def fetch(url: str) -> list[dict]:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)["data"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*")
    ap.add_argument("--embeddings", nargs="*", default=[])
    args = ap.parse_args()
    chat = {m["id"]: m for m in fetch("https://openrouter.ai/api/v1/models")}
    emb = {m["id"]: m for m in fetch("https://openrouter.ai/api/v1/embeddings/models")}
    out = {
        "retrieved_at": datetime.now(UTC).date().isoformat(),
        "source": "https://openrouter.ai/api/v1/models and /embeddings/models (USD per token)",
        "note": "Rates change; rerun this script and record the date. Long-context surcharges are ignored.",
        "models": {},
        "embeddings": {},
    }
    for mid in args.models:
        p = chat[mid]["pricing"]
        out["models"][mid] = {"prompt": float(p["prompt"]), "completion": float(p["completion"])}
    for mid in args.embeddings:
        out["embeddings"][mid] = {"per_token": float(emb[mid]["pricing"]["prompt"])}
    path = ROOT / "config" / "pricing.yaml"
    path.write_text(yaml.safe_dump(out, sort_keys=False))
    print(path.read_text())


if __name__ == "__main__":
    main()
