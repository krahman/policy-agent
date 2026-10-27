import pytest

from policy_agent import budget


def test_a_run_that_fits_is_allowed_and_one_that_does_not_is_refused():
    assert budget.check(0.20, "x", remaining=2.0) == 2.0  # needs 0.20 * 1.5 + 0.20 = 0.50
    with pytest.raises(budget.BudgetError) as e:
        budget.check(0.20, "E7", remaining=0.45)
    assert "Not started" in str(e.value) and "E7" in str(e.value)


def test_the_reserve_is_never_spent():
    assert budget.RESERVE_USD > 0
    with pytest.raises(budget.BudgetError):
        budget.check(0.0, "free run", remaining=budget.RESERVE_USD - 0.01)


def test_estimates_use_recorded_costs():
    est = budget.estimate_from_history("E7", 63, 0.5)
    assert 0.05 < est < 1.0  # about $0.19 for a full run, from eval/results/E7_dev.json
    assert budget.estimate_from_history("NOPE", 10, 0.01) == pytest.approx(0.1)


def test_exact_tests_in_the_final_analysis():
    import importlib.util
    from pathlib import Path

    import numpy as np

    spec = importlib.util.spec_from_file_location(
        "analyse_final", Path(__file__).parents[1] / "scripts" / "analyse_final.py"
    )
    af = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(af)
    a = {f"c{i}": 1.0 for i in range(8)} | {"c8": 0.0, "c9": 0.0}
    b = {f"c{i}": 0.0 for i in range(8)} | {"c8": 1.0, "c9": 0.0}
    assert af.mcnemar_exact(a, b) == (
        8,
        1,
        pytest.approx(0.0390625, abs=1e-6),
    )  # 8 vs 1 discordant pairs: p = 2*(1+9)/512
    assert af.mcnemar_exact(a, a)[2] == 1.0
    assert af.signed_rank_exact(np.array([1.0, 2.0, 3.0, 4.0, 5.0])) == pytest.approx(0.0625)  # all positive, n=5: 2/32
    assert af.signed_rank_exact(np.array([0.0, 0.0])) == 1.0
