"""Sync eval/data/*.jsonl to LangSmith datasets (PRD §11.2). The repo stays the source of truth.

Usage:
    python scripts/sync_datasets.py --dry-run   # validate and show what would be uploaded
    python scripts/sync_datasets.py             # upsert examples, remove stale ones, tag the version

Only public or synthetic data is uploaded (gold answers, public MOM quotes, synthetic memo text).
"""

import argparse
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv

from policy_agent.eval import checks
from policy_agent.eval.models import EvalCase, RedteamCase, RetrievalCase
from policy_agent.ingest.paths import PROCESSED

VERSION = "v1.1"  # v1: original labels; v1.1: F05 and K02 corrected on 2026-10-28 (see eval/LABEL_CHANGES.md)
NAMESPACE = uuid.UUID("6f1c3e0a-5b0e-4d7c-9a41-0c2e6f1d8b77")  # fixed: example ids are derived, not random


def example_id(dataset: str, case_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{dataset}/{case_id}"))


def eval_examples() -> list[dict]:
    out = []
    for c in checks.load("eval_cases.jsonl", EvalCase):
        d = c.model_dump()
        outputs = {
            k: v for k, v in d.items() if k not in ("id", "question", "user_role", "author", "created_at", "split")
        }
        out.append({
            "id": example_id("policy-eval-v1", c.id),
            "inputs": {"question": c.question, "user_role": c.user_role},
            "outputs": outputs,
            "metadata": {"case_id": c.id, "case_type": c.case_type, "author": c.author, "created_at": c.created_at,
                         "dataset_version": VERSION},
            "split": c.split,
        })  # fmt: skip
    return out


def retrieval_examples() -> list[dict]:
    return [
        {
            "id": example_id("policy-retrieval-v1", r.id),
            "inputs": {"question": r.question, "user_role": r.user_role},
            "outputs": {"relevance": r.relevance},
            "metadata": {"case_id": r.id, "dataset_version": VERSION},
            "split": r.split,
        }
        for r in checks.load("retrieval_cases.jsonl", RetrievalCase)
    ]


def redteam_examples() -> list[dict]:
    out = []
    for r in checks.load("redteam_cases.jsonl", RedteamCase):
        outputs = {
            k: v
            for k, v in r.model_dump().items()
            if k in ("expected_status", "must_contain", "must_not_contain", "must_not_endorse")
        }
        out.append({
            "id": example_id("policy-redteam-v1", r.id),
            "inputs": {"question": r.question, "user_role": r.user_role},
            "outputs": outputs,
            "metadata": {"case_id": r.id, "threat": r.threat, "kind": r.kind, "requires": r.requires,
                         "notes": r.notes, "dataset_version": VERSION},
        })  # fmt: skip
    return out


DATASETS = {
    "policy-eval-v1": ("End-to-end evaluation cases (dev/test splits)", eval_examples),
    "policy-retrieval-v1": ("Graded chunk relevance for the same questions (dev/test splits)", retrieval_examples),
    "policy-redteam-v1": ("Injection, sensitive-data, unsafe-tool and malicious-content cases", redteam_examples),
}


def corpus_fingerprint() -> str:
    return hashlib.sha256((PROCESSED / "chunks.jsonl").read_bytes()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    problems = checks.validate()
    leak = checks.leakage_report()
    if problems or not leak["clean"]:
        print("Refusing to sync: dataset fails validation or leakage checks", *problems, leak["flags"], sep="\n  ")
        return 1
    payload = {name: build() for name, (_, build) in DATASETS.items()}
    fingerprint = corpus_fingerprint()
    for name, ex in payload.items():
        splits = {s: sum(e.get("split") == s for e in ex) for s in ("dev", "test")}
        print(f"{name}: {len(ex)} examples {splits if any(splits.values()) else ''}")
    if args.dry_run:
        print(f"dry run only; corpus fingerprint {fingerprint}")
        return 0

    load_dotenv()
    from langsmith import Client

    client = Client()
    for name, (desc, _) in DATASETS.items():
        ex = payload[name]
        meta = {"version": VERSION, "corpus_chunks_sha256_12": fingerprint}
        if client.has_dataset(dataset_name=name):
            ds = client.read_dataset(dataset_name=name)
        else:
            ds = client.create_dataset(name, description=desc, metadata=meta)
        wanted = {e["id"] for e in ex}
        existing = {str(e.id) for e in client.list_examples(dataset_id=ds.id)}
        stale = sorted(existing - wanted)
        for sid in stale:
            client.delete_example(sid)
        to_create = [e for e in ex if e["id"] not in existing]
        to_update = [e for e in ex if e["id"] in existing]
        if to_create:
            client.create_examples(dataset_id=ds.id, examples=to_create)
        if to_update:  # create_examples is not an upsert: existing ids must be updated
            client.update_examples(dataset_id=ds.id, updates=to_update)
        client.update_dataset_tag(dataset_id=ds.id, as_of=datetime.now(UTC), tag=VERSION)
        got = list(client.list_examples(dataset_id=ds.id))
        splits = {}
        for e in got:
            for s in (e.metadata or {}).get("dataset_split", []) if isinstance(e.metadata, dict) else []:
                splits[s] = splits.get(s, 0) + 1
        print(
            f"synced {name}: {len(got)} examples (created {len(to_create)}, updated {len(to_update)}, "
            f"removed {len(stale)} stale), dataset id {ds.id}, splits {splits}"
        )
    print(json.dumps({"corpus_fingerprint": fingerprint, "version": VERSION}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
