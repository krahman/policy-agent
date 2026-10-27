"""Parameterised, read-only queries over data/processed/stats.duckdb. No free-form SQL ever reaches the database."""

import hashlib
import json
import threading
from collections import OrderedDict
from functools import lru_cache

import duckdb

from policy_agent.ingest.paths import CORPUS, PROCESSED
from policy_agent.mcp_server.models import (
    MAX_ROWS,
    ComputeChangeInput,
    ComputeChangeResult,
    ErrorCode,
    Method,
    QueryResult,
    QueryStatisticInput,
    Row,
    period_index,
)

DB = PROCESSED / "stats.duckdb"
TABLE = "stats_window"  # the frozen scope window (2021-Q3 to 2026-Q2) plus its annual rows
COLS = "period, value, residency, age_group, industry, industry_level, seasonal_adjustment, source_id, release_type, release_date"  # noqa: E501


class StoreError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@lru_cache(maxsize=1)
def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB), read_only=True)  # read-only: the server cannot modify the store


_lock = threading.Lock()  # one DuckDB connection, serialise cursor use
_results: OrderedDict[str, QueryResult] = OrderedDict()  # query_id -> result, so compute_change can reference it
_MAX_REMEMBERED = 64


def query_id_for(inp: QueryStatisticInput) -> str:
    blob = json.dumps(inp.model_dump(mode="json"), sort_keys=True)
    return "q-" + hashlib.sha1(blob.encode()).hexdigest()[:12]


def _one(values: list, none_ok: bool = True):
    u = set(values)
    return next(iter(u)) if len(u) == 1 else "mixed"


def query_statistic(inp: QueryStatisticInput) -> QueryResult:
    where, params = ["indicator = ?", "period_type = ?", "period >= ?", "period <= ?"], [inp.indicator.value]
    params += ["quarter" if "Q" in inp.period_from else "year", inp.period_from, inp.period_to]
    # unspecified breakdowns mean "the total", never a silent mix of breakdowns
    where += ["sex IS NULL", "qualification IS NULL"]
    for col, val in (("age_group", inp.age_group), ("industry", inp.industry)):
        if val is None:
            where.append(f"{col} IS NULL")
        else:
            where.append(f"{col} = ?")
            params.append(val.value if hasattr(val, "value") else val.lower())
    if inp.residency:
        where.append("residency = ?")
        params.append(inp.residency.value)
    if inp.seasonal_adjustment:
        where.append("seasonal_adjustment = ?")
        params.append(inp.seasonal_adjustment.value)
    sql = f"SELECT {COLS} FROM {TABLE} WHERE {' AND '.join(where)} ORDER BY period, residency, seasonal_adjustment LIMIT ?"  # noqa: S608,E501 - column names are constants, values are bound
    with _lock:
        rows = _con().execute(sql, [*params, MAX_ROWS + 1]).fetchall()
    if not rows:
        raise StoreError(ErrorCode.NO_DATA, "No rows match these filters in the scope window (2021-Q3 to 2026-Q2).")
    if len(rows) > MAX_ROWS:
        raise StoreError(ErrorCode.TOO_MANY_ROWS, f"More than {MAX_ROWS} rows match; narrow the filters.")
    out = [Row(**dict(zip(COLS.replace(" ", "").split(","), r, strict=True))) for r in rows]
    units = {r[0] for r in _units(inp)}
    warnings = []
    for label, vals in (("residency", [r.residency for r in out]), ("seasonal_adjustment", [r.seasonal_adjustment for r in out]),
                        ("source_id", [r.source_id for r in out])):  # fmt: skip
        distinct = sorted({str(v) for v in vals})
        if len(distinct) > 1:
            warnings.append(f"Results span several values of {label} ({distinct}); name one to avoid mixing measures.")
    res = QueryResult(
        query_id=query_id_for(inp), rows=out, unit=next(iter(units)) if len(units) == 1 else "mixed",
        period_type="quarter" if "Q" in inp.period_from else "year",
        seasonal_adjustment=_one([r.seasonal_adjustment for r in out]), residency=_one([r.residency for r in out]),
        source_id=_one([r.source_id for r in out]), release_type=_one([r.release_type for r in out]),
        release_date=_one([r.release_date for r in out]), warnings=warnings,
    )  # fmt: skip
    _results[res.query_id] = res
    _results.move_to_end(res.query_id)
    while len(_results) > _MAX_REMEMBERED:
        _results.popitem(last=False)
    return res


def _units(inp: QueryStatisticInput) -> list:
    with _lock:
        return (
            _con().execute(f"SELECT DISTINCT unit FROM {TABLE} WHERE indicator = ?", [inp.indicator.value]).fetchall()
        )  # noqa: S608


def compute_change(inp: ComputeChangeInput) -> ComputeChangeResult:
    unit, years, labels = inp.unit or "", inp.years, ("first", "last")
    if inp.query_id is not None:
        res = _results.get(inp.query_id)
        if res is None:
            raise StoreError(ErrorCode.UNKNOWN_QUERY_ID, "Unknown query_id; run query_statistic again.")
        groups = {(r.residency, r.age_group, r.industry, r.seasonal_adjustment) for r in res.rows}
        if len(groups) != 1:
            raise StoreError(ErrorCode.AMBIGUOUS_SERIES, "The query contains several series; narrow it to one.")
        rows = sorted(res.rows, key=lambda r: period_index(r.period))
        if len(rows) < 2:
            raise StoreError(ErrorCode.INVALID_ARGUMENT, "Need at least two periods to compute a change.")
        series, unit = [r.value for r in rows], res.unit
        labels = (rows[0].period, rows[-1].period)
        if years is None:
            years = (period_index(labels[1]) - period_index(labels[0])) / (4 if res.period_type == "quarter" else 1)
    else:
        series = list(inp.series or [])
    first, last = series[0], series[-1]
    m = inp.method
    if m is Method.pp and unit != "%":
        raise StoreError(ErrorCode.INVALID_ARGUMENT, "Percentage-point change applies only to a series in %.")
    if m in (Method.pct, Method.cagr) and first == 0:
        raise StoreError(ErrorCode.INVALID_ARGUMENT, "The first value is 0; a relative change is undefined.")
    if m is Method.cagr:
        if years is None or years <= 0:
            raise StoreError(
                ErrorCode.INVALID_ARGUMENT, "cagr needs `years` (or a query_id covering more than one period)."
            )
        if first < 0 or last < 0:
            raise StoreError(ErrorCode.INVALID_ARGUMENT, "cagr needs positive values.")
    if m is Method.abs:
        result, formula, out_unit = last - first, "last - first", unit
    elif m is Method.pp:
        result, formula, out_unit = last - first, "last - first (percentage points)", "pp"
    elif m is Method.pct:
        result, formula, out_unit = (last - first) / first * 100, "(last - first) / first * 100", "%"
    else:
        result, formula, out_unit = (
            ((last / first) ** (1 / (years or 1)) - 1) * 100,
            "((last / first) ** (1 / years) - 1) * 100",
            "% per year",
        )  # type: ignore[operator]  # noqa: E501
    inputs: dict = {"first": first, "last": last, "first_period": labels[0], "last_period": labels[1]}
    if m is Method.cagr:
        inputs["years"] = years
    return ComputeChangeResult(result=round(result, 6), method=m, formula=formula, inputs=inputs, unit=out_unit or "")


def vocabulary() -> dict:
    """What the store holds, for the stats://schema resource."""
    with _lock:
        c = _con()
        ind = c.execute(
            f"SELECT indicator, unit, period_type, MIN(period), MAX(period), COUNT(*) FROM {TABLE} GROUP BY ALL ORDER BY 1, 3"
        ).fetchall()  # noqa: S608,E501
        res = [
            r[0]
            for r in c.execute(
                f"SELECT DISTINCT residency FROM {TABLE} WHERE residency IS NOT NULL ORDER BY 1"
            ).fetchall()
        ]  # noqa: S608,E501
        sa = [r[0] for r in c.execute(f"SELECT DISTINCT seasonal_adjustment FROM {TABLE} ORDER BY 1").fetchall()]  # noqa: S608
        ages = [
            r[0]
            for r in c.execute(
                f"SELECT DISTINCT age_group FROM {TABLE} WHERE age_group IS NOT NULL ORDER BY 1"
            ).fetchall()
        ]  # noqa: S608,E501
        inds = [
            r[0]
            for r in c.execute(
                f"SELECT DISTINCT industry FROM {TABLE} WHERE industry IS NOT NULL ORDER BY 1"
            ).fetchall()
        ]  # noqa: S608,E501
    return {
        "scope_window": [CORPUS["scope_window"]["from"], CORPUS["scope_window"]["to"]],
        "indicators": [{"indicator": a, "unit": b, "period_type": c, "first_period": d, "last_period": e, "rows": n}
                       for a, b, c, d, e, n in ind],  # fmt: skip
        "residency": res, "seasonal_adjustment": sa, "age_group": ages, "industry": inds,
        "note": "seasonal_adjustment 'unspecified' means the source does not say; do not assume it is SA or NSA.",
    }  # fmt: skip


def sources() -> list[dict]:
    with _lock:
        rel = dict(_con().execute(f"SELECT source_id, MAX(release_date) FROM {TABLE} GROUP BY 1").fetchall())  # noqa: S608
    out = []
    for d in CORPUS["datagov"]:
        out.append({
            "source_id": d["key"], "dataset_id": d["dataset_id"], "indicator": d["indicator"], "period_type": d["period_type"],
            "publisher": "Ministry of Manpower, via data.gov.sg", "licence": CORPUS["licences"]["sg_odl"],
            "url": f"https://data.gov.sg/datasets/{d['dataset_id']}/view", "latest_release_date": rel.get(d["key"]),
        })  # fmt: skip
    return out
