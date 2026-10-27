import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "run_experiment", Path(__file__).parents[1] / "scripts" / "run_experiment.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def row(case_type, **scores):
    return {"case_id": "x", "case_type": case_type, "scores": scores, "latency_ms": 10.0, "cost": 0.001}


def test_aggregate_means_percentiles_and_na_handling():
    rows = [row("factual", a=1.0, b=None), row("factual", a=0.0), row("calculation", a=1.0, c="n/a")]
    agg = runner.aggregate(rows)
    assert agg["overall"]["a"] == {"mean": pytest.approx(0.6667, abs=1e-4), "n": 3}
    assert "b" not in agg["overall"] and "c" not in agg["overall"]  # None and 'n/a' stay out of averages
    assert agg["by_case_type"]["factual"]["a"]["mean"] == 0.5 and agg["by_case_type"]["calculation"]["a"]["n"] == 1
    assert agg["latency_ms"] == {"p50": 10.0, "p95": 10.0}
    assert agg["cost_usd"]["total"] == pytest.approx(0.003)


def test_test_split_needs_explicit_permission(monkeypatch, tmp_path):
    cfg_dir = Path(runner.ROOT) / "config" / "experiments"
    assert (cfg_dir / "B1.yaml").exists() and (cfg_dir / "E0.yaml").exists()
    monkeypatch.setattr("sys.argv", ["run_experiment.py", "B2_test_guard"])
    guard = cfg_dir / "B2_test_guard.yaml"
    guard.write_text("config_id: B2_test_guard\ndescription: d\ndataset: policy-eval-v1\nsplit: test\ntarget: b2\n"
                     "params: {}\nevaluators: answer\n")  # fmt: skip
    try:
        with pytest.raises(SystemExit) as e:
            runner.main()
        assert "--allow-test" in str(e.value)
    finally:
        guard.unlink()
