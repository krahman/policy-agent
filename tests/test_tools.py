import json

import pytest

from policy_agent import tools
from policy_agent.tools import calculator as calc


@pytest.mark.parametrize("expr,val", [("1 + 2 * 3", 7), ("(69900 - 127000) / 127000 * 100", -44.96), ("2 ** 10", 1024),
                                      ("abs(-3.5) + round(2.4)", 5.5), ("1,000 / 4", 250), ("-5 % 3", 1)])  # fmt: skip
def test_calculator_evaluates_plain_arithmetic(expr, val):
    assert calc.calculate(expr) == pytest.approx(val, abs=0.01)


@pytest.mark.parametrize("bad", ["__import__('os').system('ls')", "open('/etc/passwd')", "x + 1", "2 ** 99", "1 / 0", "", "'a' * 3", "().__class__", "a" * 300, "[1,2][0]", "lambda: 1"])  # fmt: skip  # noqa: E501
def test_calculator_rejects_anything_that_is_not_arithmetic(bad):
    with pytest.raises(ValueError):
        calc.calculate(bad)


def test_calculator_tool_reports_errors_as_text_not_exceptions():
    assert tools.calculator_tool.invoke({"expression": "10 / 4"}) == "10 / 4 = 2.5"
    assert tools.calculator_tool.invoke({"expression": "import os"}).startswith("Error:")


ANSWER = {"status": "answered", "summary": "Rate was 2.0%.", "confidence": "high", "limitations": ["SA basis stated"],
          "claims": [{"text": "2.0%", "kind": "statistical_finding", "tool_call_ids": ["t1"],
                      "citations": [{"source_id": "s", "chunk_id": "c", "quote": "2% (overall)"}]}]}  # fmt: skip


def test_report_rendering_labels_kinds_and_limitations():
    md = tools.render_markdown(ANSWER, "What was the rate?")
    assert "Statistical finding" in md and "t1" in md and "SA basis stated" in md and "What was the rate?" in md


def test_report_path_is_stable_and_inside_the_safe_directory():
    p = tools.report_path(ANSWER)
    assert p == tools.report_path(json.loads(json.dumps(ANSWER))) and p.parent == tools.SAFE_DIR
    assert tools.report_path({**ANSWER, "summary": "changed"}) != p  # a different answer gets a different file


def test_report_write_refuses_paths_outside_reports(tmp_path, monkeypatch):
    from policy_agent.tools import format_report as fr

    monkeypatch.setattr(fr, "SAFE_DIR", tmp_path / "reports")
    ok = fr.write_report(tmp_path / "reports" / "a.md", "x")
    assert ok.read_text() == "x"
    for bad in (tmp_path / "evil.md", tmp_path / "reports" / ".." / "evil.md", fr.Path("/etc/cron.d/brief.md")):
        with pytest.raises(PermissionError):
            fr.write_report(bad, "x")
    assert not (tmp_path / "evil.md").exists()
