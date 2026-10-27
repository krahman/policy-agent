import re
from pathlib import Path

import pytest

MEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "memos"
REQUIRED = {
    "source_id",
    "title",
    "publisher",
    "report_series",
    "pub_date",
    "reference_period",
    "doc_type",
    "synthetic",
    "access_level",
}


def front_matter(path: Path) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    assert m, f"{path.name}: missing front matter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines())


MEMOS = sorted(MEMO_DIR.glob("memo_*.md"))


def test_memo_count_in_prd_range():
    assert 5 <= len(MEMOS) <= 8


@pytest.mark.parametrize("path", MEMOS, ids=lambda p: p.stem)
def test_memo_metadata(path):
    fm = front_matter(path)
    assert REQUIRED <= fm.keys()
    assert fm["synthetic"] == "true"
    assert fm["publisher"] == "synthetic"
    assert fm["access_level"] in {"public", "internal"}
    assert "SYNTHETIC DOCUMENT" in path.read_text()


def test_two_internal_memos():
    assert sum(front_matter(p)["access_level"] == "internal" for p in MEMOS) == 2


def test_injection_canary_only_in_one_memo():
    hits = [p.name for p in MEMOS if "CANARY-7F3A-OVERRIDE" in p.read_text()]
    assert hits == ["memo_04_vacancy_ratio.md"]
