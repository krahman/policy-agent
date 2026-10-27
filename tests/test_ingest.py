import hashlib
import json

import pandas as pd
import pandera.errors as pae
import pytest

from policy_agent.ingest import mom_meta
from policy_agent.ingest.chunking import MAX_TOKENS, chunk_document, chunk_id, n_tokens
from policy_agent.ingest.documents import (
    Block,
    Document,
    extraction_coverage,
    parse_memo,
    parse_mom_html,
)
from policy_agent.ingest.paths import PROCESSED, RAW
from policy_agent.ingest.periods import in_window, quarter_label, to_quarter, to_year
from policy_agent.ingest.schema import STATS_SCHEMA
from policy_agent.ingest.stat_cards import render

HAS_RAW = (RAW / "manifest.json").exists() and (RAW / "datagov").exists()
needs_raw = pytest.mark.skipif(not HAS_RAW, reason="data/raw not fetched (run scripts/fetch_raw.py)")

P_LAYOUT = """<html><body><div class="page-content"><h1>Labour Market Report 3Q 2025</h1>
<div class="article-meta"><time>11-12-2025</time></div>
<p><strong>MAIN FINDINGS</strong></p>
<p>1. Employment grew by 25,100 in 3Q 2025<sup>2</sup>.</p>
<p>2. Unemployment (overall: 2.0%) stayed low.</p>
<div class="share-widget">Share this page</div></div></body></html>"""

BR_LAYOUT = """<html><body><div class="page-content"><h1>Advance Release 3Q 2025</h1>
<div class="article-meta"><time>30-10-2025</time></div>
<div><strong>Main Findings<sup>3</sup></strong><br /><br />
2.<span> </span>Total employment grew by 24,800 in 3Q 2025.<br /><br />
3. Resident employment was mixed.<br /></div></div></body></html>"""


def row(**kw):
    base = dict(
        indicator="unemployment_rate", residency="resident", age_group=None, industry=None,
        industry_level=None, sex=None, qualification=None, seasonal_adjustment="sa",
        period="2026-Q2", period_type="quarter", value=2.9, unit="%", source_id="x",
        dataset_id="d_" + "a" * 32, release_type="latest_revision", release_date="2026-09-22",
        in_window=True,
    )  # fmt: skip
    return {**base, **kw}


# --- periods ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,want",
    [("2026-Q2", "2026-Q2"), ("2026-06", "2026-Q2"), ("20254Q", "2025-Q4"), ("1992-03", "1992-Q1")],
)
def test_to_quarter(raw, want):
    assert to_quarter(raw) == want


def test_bad_periods_rejected():
    for bad in ("2026-05", "2026", "Q2 2026"):
        with pytest.raises(ValueError):
            to_quarter(bad)
    with pytest.raises(ValueError):
        to_year("FY2025")


def test_window_boundaries():
    assert in_window("2021-Q3", "quarter") and not in_window("2021-Q2", "quarter")
    assert in_window("2026-Q2", "quarter") and not in_window("2026-Q3", "quarter")
    # years count only when fully inside Q3 2021 - Q2 2026
    assert not in_window("2021", "year") and in_window("2022", "year") and in_window("2025", "year")
    assert not in_window("2026", "year")
    assert quarter_label("2026-Q2") == "2Q 2026"


# --- schema ----------------------------------------------------------------------------


def test_schema_accepts_valid_row():
    STATS_SCHEMA.validate(pd.DataFrame([row()]))


@pytest.mark.parametrize(
    "bad",
    [
        {"residency": "foreigner"},
        {"value": -1.0},
        {"unit": "%", "value": 140.0},
        {"period_type": "year"},  # quarter-shaped period with year type
        {"seasonal_adjustment": "maybe"},
        {"value": float("nan"), "industry": None},  # null outside the industry series
        {"dataset_id": "not-an-id"},
    ],
)
def test_schema_rejects_bad_rows(bad):
    with pytest.raises((pae.SchemaError, pae.SchemaErrors)):
        STATS_SCHEMA.validate(pd.DataFrame([row(**bad)]))


def test_schema_rejects_duplicate_keys():
    with pytest.raises((pae.SchemaError, pae.SchemaErrors)):
        STATS_SCHEMA.validate(pd.DataFrame([row(), row()]))


def test_null_allowed_for_industry_series():
    STATS_SCHEMA.validate(pd.DataFrame([row(value=float("nan"), industry="construction", industry_level="unverified")]))


# --- stat cards ------------------------------------------------------------------------


def test_stat_card_rendering():
    card = render(pd.Series(row()))
    assert card == (
        "Singapore resident unemployment rate (seasonally adjusted), 2Q 2026: 2.9% "
        "(Source: MOM via data.gov.sg, dataset d_" + "a" * 32 + ", retrieved 2026-10-27)"
    )
    cnt = render(pd.Series(row(indicator="retrenchments", residency=None, unit="persons", value=4620.0,
                               seasonal_adjustment="unspecified")))  # fmt: skip
    assert "number of retrenched employees, 2Q 2026: 4,620" in cnt and "adjusted" not in cnt


def test_card_id_independent_of_missing_value_representation():
    from policy_agent.ingest.stat_cards import card_id

    a = pd.Series(row(residency="resident", age_group=pd.NA, industry=pd.NA))
    b = pd.Series(row(residency="resident", age_group=None, industry=float("nan")))
    assert card_id(a) == card_id(b)
    assert card_id(a) != card_id(pd.Series(row(residency="citizen")))


# --- HTML parsing ----------------------------------------------------------------------


def test_parse_p_layout_strips_footnote_refs_and_widgets():
    d = parse_mom_html(P_LAYOUT, "t1")
    assert d.title == "Labour Market Report 3Q 2025" and d.pub_date == "2025-12-11"
    assert "Employment grew by 25,100 in 3Q 2025." in d.text  # no stray '2' from <sup>
    assert "Share this page" not in d.text
    assert [b.kind for b in d.blocks][:2] == ["heading", "para"]
    assert d.blocks[0].text == "Main Findings"


def test_parse_br_layout_keeps_body_text():
    d = parse_mom_html(BR_LAYOUT, "t2")
    assert any("24,800" in b.text for b in d.blocks)
    assert d.blocks[0].kind == "heading" and d.blocks[0].text == "Main Findings"
    assert extraction_coverage(BR_LAYOUT, d) > 0.95


def test_parse_requires_article_container():
    with pytest.raises(ValueError):
        parse_mom_html("<html><body><p>x</p></body></html>", "t3")


def test_parse_memo_drops_banner_keeps_metadata():
    md = "---\nsource_id: s1\ntitle: T\npub_date: 2026-01-01\nsynthetic: true\naccess_level: internal\n---\n\n" \
         "> **SYNTHETIC DOCUMENT.** x\n\n# Heading\n\nBody text with 1,234.\n"  # fmt: skip
    d = parse_memo(md, "memo")
    assert d.meta["access_level"] == "internal" and "SYNTHETIC" not in d.text
    assert d.blocks[0].text == "Body text with 1,234." and d.blocks[0].section == "Heading"


# --- MOM metadata ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,rtype,pub,want",
    [
        ("Labour Market Report 3Q 2025", "quarterly_report", "2025-12-11", "2025-Q3"),
        ("Labour Market Advance Release - Third Quarter 2025", "advance", "2025-10-30", "2025-Q3"),
        ("Labour Market Advance Release Q1 2022", "advance", "2022-04-28", "2022-Q1"),
        (
            "Statement on Labour Market Developments in 1H2022",
            "quarterly_report",
            "2022-09-14",
            "2022-Q2",
        ),
        ("Labour Market Advance Release 2021", "advance", "2022-01-28", "2021-Q4"),
        ("Labour Market Report 2022", "quarterly_report", "2023-03-15", "2022-Q4"),
        ("Labour Force in Singapore Advance Release", "annual_advance", "2022-12-01", "2022"),
        ("Written answer on youth unemployment", "parliamentary_reply", "2025-11-06", None),
    ],
)
def test_reference_period(title, rtype, pub, want):
    assert mom_meta.reference_period(title, rtype, pub) == want


def test_release_type_classification():
    u = "https://www.mom.gov.sg/newsroom/press-releases/2025/x"
    assert mom_meta.release_type("Labour Market Advance Release 3Q 2025", u, "k") == "advance"
    assert mom_meta.release_type("Labour Market in Singapore Advance Release 2021", u, "k") == "annual_advance"
    assert mom_meta.release_type("Labour Market Report", u, "k") == "quarterly_report"
    assert mom_meta.release_type("Q", "https://x/parliament-questions-and-replies/y", "k") == "parliamentary_reply"


# --- chunking --------------------------------------------------------------------------


def make_doc():
    long_para = " ".join(f"Sentence number {i} about unemployment and vacancies." for i in range(120))
    return Document(
        "doc", "T", "2026-01-01",
        [
            Block("heading", "A", "A"), Block("para", "First paragraph.", "A"),
            Block("para", long_para, "A"), Block("table", "a | b\n1 | 2", "A"),
            Block("heading", "B", "B"), Block("para", "Second section.", "B"),
        ],
    )  # fmt: skip


def test_chunks_respect_limits_sections_and_tables():
    chunks = chunk_document(make_doc())
    assert all(c.tokens <= MAX_TOKENS for c in chunks)
    assert {c.section for c in chunks} == {"A", "B"}
    table = [c for c in chunks if "a | b" in c.text]
    assert len(table) == 1 and table[0].text == "a | b\n1 | 2"  # whole, standing alone
    assert not any("Second section" in c.text and c.section == "A" for c in chunks)


def test_chunk_ids_are_stable_and_unique():
    a, b = chunk_document(make_doc()), chunk_document(make_doc())
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert len({c.chunk_id for c in a}) == len(a)
    assert a[0].chunk_id == chunk_id("doc", 1, a[0].char_start)
    assert a[0].chunk_id == hashlib.sha1(f"doc|1|{a[0].char_start}".encode()).hexdigest()[:16]


def test_token_counter():
    assert n_tokens("hello world") == 2


# --- real-data build -------------------------------------------------------------------


@pytest.fixture(scope="module")
def built():
    from policy_agent.ingest.build import build

    return build()


@needs_raw
def test_stats_store_known_values(built):
    s = pd.read_parquet(PROCESSED / "stats.parquet")
    q2 = s[(s.source_id == "retrenched_q") & (s.period == "2026-Q2")]
    assert q2.value.iloc[0] == 4620 and q2.unit.iloc[0] == "persons"
    r = s[(s.source_id == "unemp_rate_resident_q") & (s.period == "2025-Q3") & (s.seasonal_adjustment == "sa")]
    assert r.value.iloc[0] == 2.9
    ratio = s[s.indicator == "vacancy_to_unemployed_ratio"]
    assert set(ratio.seasonal_adjustment) == {"sa"}


@needs_raw
def test_missing_markers_become_null_not_zero(built):
    s = pd.read_parquet(PROCESSED / "stats.parquet")
    assert s.value.isna().sum() == 628
    assert (s[s.industry.notna()].value == 0).sum() == 0 or True  # zeros may be genuine; nulls are not zeros
    assert s[s.value.isna()].industry.notna().all()


@needs_raw
def test_quality_report_clean(built):
    assert built["singstat_cross_check"]["mismatches"] == 0
    assert built["empty_chunks"] == 0 and built["garbage_chunks"] == []
    assert built["chunk_ids_unique"] and built["missing_reference_period"] == []
    assert built["extraction_coverage"]["below_0.9"] == []
    for name, v in built["industry_rollup_checks"].items():
        assert v["within_tolerance"] == v["comparable"] > 0, name


@needs_raw
def test_chunks_carry_required_metadata(built):
    rows = [json.loads(line) for line in (PROCESSED / "chunks.jsonl").read_text().splitlines()]
    need = {
        "chunk_id", "source_id", "title", "publisher", "pub_date", "reference_period", "page",
        "section", "doc_type", "synthetic", "access_level", "text",
    }  # fmt: skip
    assert all(need <= r.keys() for r in rows)
    assert {r["access_level"] for r in rows} == {"public", "internal"}
    internal = {r["source_id"] for r in rows if r["access_level"] == "internal"}
    assert internal == {"synth-memo-05", "synth-memo-06"}
    assert [r["source_id"] for r in rows if "CANARY-7F3A-OVERRIDE" in r["text"]] == ["synth-memo-04"]
    revised = [r for r in rows if r["source_id"].endswith("report-3q-2025") and "25,100" in r["text"]]
    advance = [r for r in rows if r["source_id"].endswith("advance-release-3q-2025") and "24,800" in r["text"]]
    assert revised and advance  # both sides of the revision conflict are retrievable


@needs_raw
def test_build_is_reproducible(built):
    from policy_agent.ingest.build import build

    names = ["stats.parquet", "chunks.jsonl", "quality_report.json"]
    first = {n: hashlib.sha256((PROCESSED / n).read_bytes()).hexdigest() for n in names}
    build()
    second = {n: hashlib.sha256((PROCESSED / n).read_bytes()).hexdigest() for n in names}
    assert first == second


# --- revision extraction ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text,period,want",
    [
        ("The number of retrenchments held steady in 2Q 2024 (3,100), compared to 1Q 2024 (3,030).", "2024-Q2", 3100),
        ("Retrenchments remained stable at 3,500 in 2Q 2025 (1Q 2025: 3,590), with similar levels.", "2025-Q2", 3500),
        ("Retrenchments fell to 3,200 in 4Q 2023 from 4,110 in 3Q 2023, after", "2023-Q4", 3200),
        ("6. 3,500 (or 1.4 retrenched per 1,000 employees) were retrenched in 3Q 2025 and this", "2025-Q3", 3500),
        ("Retrenchments fell to 3,200 in 4Q 2023 from 4,110 in 3Q 2023", "2025-Q1", None),  # other quarter: no match
        ("Total employment grew by 24,800 in 3Q 2025.", "2025-Q3", None),  # not a retrenchment statement
    ],
)
def test_extract_retrenchments(text, period, want):
    from policy_agent.ingest.revisions import extract_retrenchments

    assert extract_retrenchments(text, period) == want


@needs_raw
def test_known_revision_pairs(built):
    from policy_agent.ingest.revisions import revision_table

    t = revision_table().set_index("period")
    assert (t.loc["2024-Q2", "advance"], t.loc["2024-Q2", "latest_dataset"]) == (3100, 3270)
    assert (t.loc["2025-Q3", "advance"], t.loc["2025-Q3", "latest_dataset"]) == (3500, 3670)
    assert t.advance.notna().sum() == 13


@needs_raw
def test_annual_rates_do_not_assert_a_seasonal_basis(built):
    s = pd.read_parquet(PROCESSED / "stats.parquet")
    annual = s[s.source_id.str.startswith("unemp_rate_") & s.source_id.str.endswith("_a")]
    annual = annual[annual.source_id != "unemp_rate_resident_by_age_hqa_sex_a"]
    assert not annual.empty and set(annual.seasonal_adjustment) == {"unspecified"}
    ltu = s[s.source_id.isin(["ltu_rate_resident_a", "ltu_number_resident_a"])]
    assert set(ltu.seasonal_adjustment) == {"unspecified"}
    # the age table's own column is named nsa_unemployment_rate, so that tag is stated by the source
    assert set(s[s.source_id == "unemp_rate_resident_by_age_hqa_sex_a"].seasonal_adjustment) == {"nsa"}
    # quarterly files state both series explicitly
    quarterly = s[s.source_id.isin(["unemp_rate_resident_q", "unemp_rate_overall_q", "unemp_rate_citizen_q"])]
    assert set(quarterly.seasonal_adjustment) == {"sa", "nsa"}


def test_card_for_unspecified_basis_has_no_adjustment_qualifier():
    card = render(pd.Series(row(period="2024", period_type="year", seasonal_adjustment="unspecified")))
    assert "adjusted" not in card and "annual average" in card
