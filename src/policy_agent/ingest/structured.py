"""Load data.gov.sg CSVs into one tidy long table."""

import json
from datetime import datetime

import pandas as pd

from policy_agent.ingest.paths import CORPUS, RAW
from policy_agent.ingest.periods import in_window, to_quarter, to_year

TIDY_COLUMNS = [
    "indicator", "residency", "age_group", "industry", "industry_level", "sex", "qualification",
    "seasonal_adjustment", "period", "period_type", "value", "unit",
    "source_id", "dataset_id", "release_type", "release_date", "in_window",
]  # fmt: skip

# Industry roll-ups verified numerically against their components (see tests / quality report).
INDUSTRY_ROLLUPS = {
    "financial and insurance services": ["financial services", "insurance services"],
    "accommodation and food services": ["accommodation", "food and beverage services"],
    "wholesale and retail trade": ["wholesale trade", "retail trade"],
}
_COMPONENTS = {c for cs in INDUSTRY_ROLLUPS.values() for c in cs}


def _industry_level(name: str) -> str:
    if name in INDUSTRY_ROLLUPS:
        return "aggregate"
    return "component" if name in _COMPONENTS else "unverified"


def _num(s: pd.Series) -> pd.Series:
    """data.gov.sg encodes missing values as '-'; they become NaN, never 0."""
    return pd.to_numeric(s.replace("-", pd.NA), errors="coerce")


def _release_date(key: str) -> str:
    """Catalogue lastUpdatedAt (date only). contactEmails in the metadata is never read."""
    meta = json.loads((RAW / "datagov" / f"{key}.meta.json").read_text())["data"]
    return datetime.fromisoformat(meta["lastUpdatedAt"]).date().isoformat()


def _finish(df: pd.DataFrame, item: dict, period_type: str) -> pd.DataFrame:
    for col in TIDY_COLUMNS:
        if col not in df:
            df[col] = pd.NA
    df["indicator"] = item["indicator"]
    df["period_type"] = period_type
    df["source_id"] = item["key"]
    df["dataset_id"] = item["dataset_id"]
    df["release_type"] = "latest_revision"
    df["release_date"] = _release_date(item["key"])
    df["in_window"] = [in_window(p, period_type) for p in df["period"]]
    return df[TIDY_COLUMNS]


def _read(key: str) -> pd.DataFrame:
    return pd.read_csv(RAW / "datagov" / f"{key}.csv", dtype=str, encoding="utf-8-sig")


def _rate_or_count_q(item: dict, unit: str, sa_col: str, nsa_col: str) -> pd.DataFrame:
    raw = _read(item["key"])
    parts = []
    for col, sa in ((sa_col, "sa"), (nsa_col, "nsa")):
        parts.append(
            pd.DataFrame(
                {
                    "residency": raw["residential_status"],
                    "period": [to_quarter(p) for p in raw["period"]],
                    "value": _num(raw[col]),
                    "seasonal_adjustment": sa,
                }
            )
        )
    df = pd.concat(parts, ignore_index=True)
    df["unit"] = unit
    return _finish(df, item, "quarter")


def _load_one(item: dict) -> pd.DataFrame:
    key = item["key"]
    if key.startswith("unemp_rate_") and key.endswith("_q"):
        return _rate_or_count_q(item, "%", "seasonally_adj_unemp_rate", "non_seasonally_adj_unemp_rate")
    if key.startswith("unemployed_") and key.endswith("_q"):
        return _rate_or_count_q(item, "persons", "seasonally_adj_unemp", "non_seasonally_adj_unemp")
    raw = _read(key)
    if key.startswith("unemp_rate_") and key.endswith("_a") and "by_age" not in key:
        df = pd.DataFrame(
            {
                "residency": raw["residential_status"],
                "period": [to_year(y) for y in raw["year"]],
                "value": _num(raw["unemployment_rate"]),
                "seasonal_adjustment": "nsa",  # annual average of quarterly NSA figures
                "unit": "%",
            }
        )
        return _finish(df, item, "year")
    if key == "unemp_rate_resident_by_age_hqa_sex_a":
        df = pd.DataFrame(
            {
                "residency": "resident",
                "age_group": raw["age"],
                "sex": raw["sex"],
                "qualification": raw["highest_qualification_attained"],
                "period": [to_year(y) for y in raw["year"]],
                "value": _num(raw["nsa_unemployment_rate"]),
                "seasonal_adjustment": "nsa",
                "unit": "%",
            }
        )
        return _finish(df, item, "year")
    if key in ("ltu_rate_resident_a", "ltu_number_resident_a"):
        is_rate = key == "ltu_rate_resident_a"
        df = pd.DataFrame(
            {
                "residency": raw["residential_status"],
                "period": [to_year(y) for y in raw["year"]],
                "value": _num(raw["ltu_rate" if is_rate else "long_term_unemployed"]),
                "seasonal_adjustment": "nsa",
                "unit": "%" if is_rate else "persons",
            }
        )
        item = {
            **item,
            "indicator": "long_term_unemployment_rate" if is_rate else "long_term_unemployed_persons",
        }
        return _finish(df, item, "year")
    # level / ratio series: quarter or year, optional industry
    period_type = item["period_type"]
    pcol = "quarter" if period_type == "quarter" else "year"
    vcol = {
        "retrenchments": "retrench",
        "job_vacancies": "job_vacancy",
        "vacancy_to_unemployed_ratio": "jv_to_ue",
    }[item["indicator"]]
    norm = to_quarter if period_type == "quarter" else to_year
    ratio = item["indicator"] == "vacancy_to_unemployed_ratio"
    df = pd.DataFrame(
        {
            "period": [norm(p) for p in raw[pcol]],
            "value": _num(raw[vcol]),
            "seasonal_adjustment": "sa" if ratio else "unspecified",  # ratio datasets state SA
            "unit": "ratio" if ratio else "persons",
        }
    )
    if "industry" in raw:
        df["industry"] = raw["industry"].values
        df["industry_level"] = [_industry_level(i) for i in df["industry"]]
    return _finish(df, item, period_type)


def load_structured() -> pd.DataFrame:
    frames = [_load_one(item) for item in CORPUS["datagov"] if item["key"] != "singstat_unemp_rate_sa_q"]
    df = pd.concat(frames, ignore_index=True)
    sort_cols = ["indicator", "source_id", "residency", "age_group", "industry", "sex", "qualification",
                 "seasonal_adjustment", "period"]  # fmt: skip
    return df.sort_values(sort_cols, na_position="first", kind="stable").reset_index(drop=True)


def load_singstat_sa() -> pd.DataFrame:
    """Wide SingStat SA table -> long (residency, period, value); used only for cross-checks."""
    raw = pd.read_csv(RAW / "datagov" / "singstat_unemp_rate_sa_q.csv", dtype=str, encoding="utf-8-sig")
    long = raw.melt(id_vars="DataSeries", var_name="p", value_name="v")
    long["residency"] = long["DataSeries"].str.extract(r"^(Total|Resident|Citizen)")[0].str.lower()
    long["residency"] = long["residency"].replace({"total": "overall"})
    long["period"] = [to_quarter(p) for p in long["p"]]
    long["value"] = _num(long["v"])
    return long[["residency", "period", "value"]].dropna(subset=["residency"])
