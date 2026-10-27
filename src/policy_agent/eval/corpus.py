"""Look gold answers up in the processed corpus so labels cannot drift from the data."""

import json
from functools import cached_property

import pandas as pd

from policy_agent.ingest.paths import PROCESSED
from policy_agent.ingest.stat_cards import card_id


class Corpus:
    @cached_property
    def stats(self) -> pd.DataFrame:
        return pd.read_parquet(PROCESSED / "stats.parquet")

    @cached_property
    def chunks(self) -> list[dict]:
        return [json.loads(line) for line in (PROCESSED / "chunks.jsonl").read_text().splitlines()]

    @cached_property
    def chunk_by_id(self) -> dict[str, dict]:
        return {c["chunk_id"]: c for c in self.chunks}

    def row(self, source_id: str, period: str, residency: str | None = None, sa: str | None = None) -> pd.Series:
        s = self.stats
        m = (s.source_id == source_id) & (s.period == period)
        if residency:
            m &= s.residency == residency
        if sa:
            m &= s.seasonal_adjustment == sa
        hit = s[m & s.industry.isna() & s.age_group.isna()]
        if len(hit) != 1:
            raise LookupError(f"{source_id} {period} {residency} {sa}: {len(hit)} rows")
        return hit.iloc[0]

    def value(self, *args, **kw) -> float:
        return float(self.row(*args, **kw).value)

    def card(self, *args, **kw) -> str:
        """chunk_id of the stat card for a structured row (must exist in chunks.jsonl)."""
        cid = card_id(self.row(*args, **kw))
        if cid not in self.chunk_by_id:
            raise LookupError(f"no stat card chunk {cid} for {args} {kw}")
        return cid

    def passage(self, source: str, contains: str) -> dict:
        """The single prose chunk from a source (substring of source_id) containing `contains`."""
        hits = [c for c in self.chunks if source in c["source_id"] and contains in c["text"]]
        if len(hits) != 1:
            raise LookupError(f"{source!r} / {contains!r}: {len(hits)} chunks")
        return hits[0]
