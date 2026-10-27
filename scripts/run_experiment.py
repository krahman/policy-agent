"""Run one experiment config (config/experiments/<id>.yaml) over a dataset split and record the results.

Usage:
    python scripts/run_experiment.py B1                  # run in LangSmith, write eval/results/<id>_<split>.json
    python scripts/run_experiment.py B1 --local          # run on the JSONL files, no upload
    python scripts/run_experiment.py B1 --local --limit 3
Only `dev` may be used while tuning; `test` needs --allow-test and should be run once per frozen configuration.
"""

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from policy_agent.eval import evaluators as ev  # noqa: E402
from policy_agent.eval.evaluators import cost_usd, pricing  # noqa: E402

DATASET_VERSION = "v1"


def git_info() -> dict:
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout.strip()

    return {
        "git_sha": run("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)eval/results")),
    }


def build_target(cfg: dict):
    t, p = cfg["target"], cfg.get("params") or {}
    if t == "b0":
        from policy_agent.baselines import b0

        return b0.run, {"retriever": "bm25", "chunker": "C2", "k": p.get("k", 10)}
    if t == "b2":
        from policy_agent.baselines import b2

        return b2.run, {"retriever": "none (table lookup)"}
    if t == "b1":
        from policy_agent.baselines import b1

        run, prompt = b1.make_target(p["model"], p["embedding"], p["k"], p.get("max_tokens", 1500))
        return run, {
            "retriever": "dense", "chunker": "C2", "model": p["model"], "embedding": p["embedding"], "k": p["k"],
            "temperature": p.get("temperature", 0), "prompt": f"{prompt['name']}@{prompt['version']}",
            "prompt_sha256_12": prompt["sha256_12"],
        }  # fmt: skip
    raise SystemExit(f"unknown target {t!r}")


def local_examples(dataset: str, split: str, limit: int | None) -> list[dict]:
    import sync_datasets as sd

    make = {"policy-eval-v1": sd.eval_examples, "policy-retrieval-v1": sd.retrieval_examples}[dataset]
    rows = [e for e in make() if e.get("split") == split]
    return rows[:limit] if limit else rows


def aggregate(rows: list[dict]) -> dict:
    """rows: [{case_id, case_type, scores {key: float|None}, latency_ms, cost}] -> overall and per case type."""

    def mean_by(rs: list[dict]) -> dict:
        keys = sorted({k for r in rs for k in r["scores"]})
        out = {}
        for k in keys:
            # vals = [r["scores"][k] for r in rs if isinstance(r["scores"].get(k), (int, float))]
            vals = [r["scores"][k] for r in rs if isinstance(r["scores"].get(k), int | float)]
            if vals:
                out[k] = {"mean": round(statistics.fmean(vals), 4), "n": len(vals)}
        return out

    lat = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[r["case_type"]].append(r)
    q = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 1) if lat else None  # noqa: E731
    return {
        "n_runs": len(rows),
        "overall": mean_by(rows),
        "by_case_type": {t: mean_by(rs) for t, rs in sorted(by_type.items())},
        "latency_ms": {"p50": q(0.5), "p95": q(0.95)},
        "cost_usd": {"total": round(sum(r.get("cost", 0) for r in rows), 5),
                     "mean_per_run": round(sum(r.get("cost", 0) for r in rows) / max(len(rows), 1), 6)},
    }  # fmt: skip


def score_row(example: dict, outputs: dict, evaluators: list) -> dict:
    scores = {}
    for fn in evaluators:
        res = fn(outputs=outputs, reference_outputs=example["outputs"])
        scores[res["key"]] = res.get("score")
    meta = example["metadata"]
    return {"case_id": meta["case_id"], "case_type": meta.get("case_type", "retrieval"), "scores": scores,
            "latency_ms": outputs.get("latency_ms"), "cost": cost_usd(outputs.get("usage")),
            "status": outputs.get("error") or outputs.get("status")}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config_id")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--allow-test", action="store_true")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    cfg = yaml.safe_load((ROOT / "config" / "experiments" / f"{args.config_id}.yaml").read_text())
    if cfg["split"] == "test" and not args.allow_test:
        raise SystemExit("refusing to run the test split without --allow-test (run once per frozen configuration)")
    evaluators = ev.ANSWER_EVALUATORS if cfg["evaluators"] == "answer" else ev.RETRIEVAL_EVALUATORS
    target, tmeta = build_target(cfg)
    chunks_sha = hashlib.sha256((ROOT / "data" / "processed" / "chunks.jsonl").read_bytes()).hexdigest()[:12]
    metadata = {
        "config_id": cfg["config_id"], **git_info(), **tmeta, "dataset": cfg["dataset"],
        "dataset_version": DATASET_VERSION,
        "split": cfg["split"], "corpus_chunks_sha256_12": chunks_sha, "pricing_retrieved_at": pricing()["retrieved_at"],
        "seed": "n/a (temperature 0)", "python": platform.python_version(),
    }  # fmt: skip

    if args.local:
        rows = []
        for ex in local_examples(cfg["dataset"], cfg["split"], args.limit):
            rows.append(score_row(ex, target(ex["inputs"]), evaluators))
        for r in rows:
            print(
                f"{r['case_id']:4} {r['case_type']:12}",
                {
                    k: (round(v, 2) if isinstance(v, float) else v)
                    for k, v in r["scores"].items()
                    if v is not None and k not in ("latency_ms", "est_cost_usd")
                },
            )  # noqa: E501
        print(json.dumps(aggregate(rows)["overall"], indent=1)[:1500])
        return 0

    from langsmith import Client, evaluate

    client = Client()
    t0 = time.time()
    results = evaluate(
        lambda inputs: target(inputs),
        data=client.list_examples(dataset_name=cfg["dataset"], splits=[cfg["split"]], limit=args.limit),
        evaluators=evaluators,
        experiment_prefix=cfg["config_id"],
        description=cfg["description"],
        metadata=metadata,
        num_repetitions=cfg.get("repetitions", 1),
        max_concurrency=cfg.get("max_concurrency", 2),
        client=client,
    )
    rows = []
    for r in results:
        run, example = r["run"], r["example"]
        scores = {x.key: x.score for x in r["evaluation_results"]["results"]}
        rows.append({
            "case_id": example.metadata["case_id"], "case_type": example.metadata.get("case_type", "retrieval"),
            "scores": scores, "latency_ms": (run.outputs or {}).get("latency_ms"),
            "cost": cost_usd((run.outputs or {}).get("usage")), "status": (run.outputs or {}).get("status"),
        })  # fmt: skip
    agg = aggregate(rows)
    url = None
    try:
        url = client.read_project(project_name=results.experiment_name).url
    except Exception:  # noqa: BLE001
        pass
    out = {"experiment": results.experiment_name, "url": url, "metadata": metadata, "config": cfg,
           "wall_seconds": round(time.time() - t0, 1), **agg, "runs": rows}  # fmt: skip
    path = ROOT / "eval" / "results" / f"{cfg['config_id']}_{cfg['split']}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n")
    print(f"experiment {results.experiment_name}\nurl {url}\nwrote {path.relative_to(ROOT)}")
    print(json.dumps(agg["overall"], indent=1)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
