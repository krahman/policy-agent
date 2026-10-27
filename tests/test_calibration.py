import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "calibrate_judge", Path(__file__).parents[1] / "scripts" / "calibrate_judge.py"
)
cal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cal)


def test_kappa_perfect_chance_and_degenerate():
    assert cal.cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert abs(cal.cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])) < 1e-9  # agreement no better than chance
    assert cal.cohen_kappa([1, 1], [1, 1]) is None  # no variation: kappa undefined
    assert cal.cohen_kappa([], []) is None


def test_read_labels_only_counts_ticked_boxes():
    sheet = """
- [x] supported <!--g:01-F02:1:1-->
- [ ] not supported <!--g:01-F02:1:0-->
- [ ] supported <!--g:01-F02:2:1-->
- [X] not supported <!--g:01-F02:2:0-->
- [x] supported <!--g:01-F02:3:1-->
- [x] not supported <!--g:01-F02:3:0-->
- [ ] 2 <!--r:01-F02:2-->
- [x] 4 <!--r:01-F02:4-->
"""
    g, r = cal.read_labels(sheet)
    assert g[("01-F02", 1)] == {1} and g[("01-F02", 2)] == {0} and g[("01-F02", 3)] == {0, 1}
    assert r == {"01-F02": {4}}
