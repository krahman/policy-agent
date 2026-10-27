"""pandera schema for the tidy stats table (PRD §5.2 quality checks)."""

import pandera.pandas as pa

INDICATORS = [
    "unemployment_rate", "unemployed_persons", "long_term_unemployment_rate",
    "long_term_unemployed_persons", "retrenchments", "job_vacancies", "vacancy_to_unemployed_ratio",
]  # fmt: skip
RESIDENCY = ["overall", "resident", "citizen"]
SEASONAL = ["sa", "nsa", "unspecified"]
KEY = ["indicator", "residency", "age_group", "industry", "sex", "qualification",
       "seasonal_adjustment", "period", "source_id"]  # fmt: skip

STATS_SCHEMA = pa.DataFrameSchema(
    {
        "indicator": pa.Column(str, pa.Check.isin(INDICATORS)),
        "residency": pa.Column(str, pa.Check.isin(RESIDENCY), nullable=True),
        "age_group": pa.Column(str, nullable=True),
        "industry": pa.Column(str, nullable=True),
        "industry_level": pa.Column(str, pa.Check.isin(["aggregate", "component", "unverified"]), nullable=True),
        "sex": pa.Column(str, nullable=True),
        "qualification": pa.Column(str, nullable=True),
        "seasonal_adjustment": pa.Column(str, pa.Check.isin(SEASONAL)),
        "period": pa.Column(str),
        "period_type": pa.Column(str, pa.Check.isin(["quarter", "year"])),
        # NaN is allowed only for the documented '-' markers (industry series)
        "value": pa.Column(float, pa.Check.ge(0), nullable=True),
        "unit": pa.Column(str, pa.Check.isin(["%", "persons", "ratio"])),
        "source_id": pa.Column(str),
        "dataset_id": pa.Column(str, pa.Check.str_matches(r"^d_[0-9a-f]{32}$")),
        "release_type": pa.Column(str),
        "release_date": pa.Column(str, pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}$")),
        "in_window": pa.Column(bool),
    },
    checks=[
        pa.Check(
            lambda df: ~((df["period_type"] == "quarter") ^ df["period"].str.match(r"^\d{4}-Q[1-4]$")),
            error="period format must match period_type",
        ),
        pa.Check(
            lambda df: ~((df["unit"] == "%") & (df["value"] > 100)),
            error="percentage above 100",
        ),
        pa.Check(
            lambda df: ~df.duplicated(subset=KEY, keep=False),
            error="duplicate key rows",
        ),
        pa.Check(
            lambda df: df["value"].notna() | df["industry"].notna(),
            error="null value outside the industry series",
        ),
    ],
    strict=True,
    coerce=False,
)
