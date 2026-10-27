"""Contract shared by the MCP server and the client wrapper: inputs, outputs and error codes (PRD §10.1).

`extra="forbid"` everywhere, so an unexpected field in a server response is a validation failure on the client."""

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_PERIODS = 40
MAX_SERIES = 100
MAX_ROWS = 500
PERIOD_RE = re.compile(r"^\d{4}(-Q[1-4])?$")


class Indicator(StrEnum):
    unemployment_rate = "unemployment_rate"
    unemployed_persons = "unemployed_persons"
    long_term_unemployment_rate = "long_term_unemployment_rate"
    long_term_unemployed_persons = "long_term_unemployed_persons"
    retrenchments = "retrenchments"
    job_vacancies = "job_vacancies"
    vacancy_to_unemployed_ratio = "vacancy_to_unemployed_ratio"


class Residency(StrEnum):
    overall = "overall"
    resident = "resident"
    citizen = "citizen"


class AgeGroup(StrEnum):
    a15_29 = "15-29"
    a30_39 = "30-39"
    a40_49 = "40-49"
    a50_plus = "50 and over"


class SeasonalAdjustment(StrEnum):
    sa = "sa"
    nsa = "nsa"
    unspecified = "unspecified"


class Method(StrEnum):
    abs = "abs"
    pct = "pct"
    pp = "pp"
    cagr = "cagr"


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NO_DATA = "NO_DATA"
    TOO_MANY_ROWS = "TOO_MANY_ROWS"
    UNKNOWN_QUERY_ID = "UNKNOWN_QUERY_ID"
    AMBIGUOUS_SERIES = "AMBIGUOUS_SERIES"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"


def period_index(p: str) -> int:
    """Quarter index (year*4 + q-1) for 'YYYY-Qn', or the year for 'YYYY'; only comparable within one period type."""
    return int(p[:4]) * 4 + int(p[-1]) - 1 if "Q" in p else int(p)


class QueryStatisticInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator: Indicator
    period_from: str = Field(pattern=PERIOD_RE.pattern)
    period_to: str = Field(pattern=PERIOD_RE.pattern)
    residency: Residency | None = None
    age_group: AgeGroup | None = None
    industry: str | None = Field(default=None, max_length=80)
    seasonal_adjustment: SeasonalAdjustment | None = None

    @model_validator(mode="after")
    def _range(self):
        a, b = self.period_from, self.period_to
        if ("Q" in a) != ("Q" in b):
            raise ValueError("period_from and period_to must both be years (YYYY) or both quarters (YYYY-Qn)")
        if period_index(a) > period_index(b):
            raise ValueError("period_from is after period_to")
        if period_index(b) - period_index(a) + 1 > MAX_PERIODS:
            raise ValueError(f"range is longer than {MAX_PERIODS} periods")
        return self


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str
    value: float
    residency: str | None = None
    age_group: str | None = None
    industry: str | None = None
    industry_level: str | None = None
    seasonal_adjustment: str
    source_id: str
    release_type: str
    release_date: str


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(pattern=r"^q-[0-9a-f]{12}$")
    rows: list[Row]
    unit: str
    period_type: Literal["quarter", "year"]
    # these are set when every row agrees, otherwise "mixed" so the caller cannot mistake a mix for one basis
    seasonal_adjustment: str
    residency: str | None
    source_id: str
    release_type: str
    release_date: str
    warnings: list[str] = []


class ComputeChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Method
    query_id: str | None = Field(default=None, pattern=r"^q-[0-9a-f]{12}$")
    series: list[float] | None = Field(default=None, min_length=2, max_length=MAX_SERIES)
    unit: str | None = Field(default=None, max_length=20)
    years: float | None = Field(default=None, gt=0, le=200)

    @field_validator("series")
    @classmethod
    def _finite(cls, v):
        if v is not None and any(x != x or abs(x) == float("inf") for x in v):
            raise ValueError("series must be finite numbers")
        return v

    @model_validator(mode="after")
    def _one_source(self):
        if (self.query_id is None) == (self.series is None):
            raise ValueError("give exactly one of query_id or series")
        return self


class ComputeChangeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: float
    method: Method
    formula: str
    inputs: dict[str, float | str | None]
    unit: str


class ToolErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(max_length=500)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    dataset_id: str
    indicator: str
    period_type: str
    publisher: str
    licence: str
    url: str
    latest_release_date: str | None = None


class SourcesDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[Source]


class SchemaDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_window: list[str]
    indicators: list[dict[str, str | int]]
    residency: list[str]
    seasonal_adjustment: list[str]
    age_group: list[str]
    industry: list[str]
    note: str
