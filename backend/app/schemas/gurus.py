from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class GuruOut(BaseModel):
    """A well-known investor and the state of their stored snapshot."""

    id: str
    name_ko: str
    name_en: str
    source: Literal["ark", "13f"]
    # Standing caveat about the source (ETF not a personal account, 13F is long-only, ...).
    note: str
    synced_at: datetime | None
    # Date the holdings describe: ARK's file date, or the 13F quarter end.
    as_of: date | None
    # No snapshot yet, the last sync failed, or the snapshot is older than the source's cadence.
    stale: bool
    error: str | None
    # Non-fatal caveats from the last sync (e.g. fund files excluded as stale).
    sync_note: str | None
    holdings_count: int


class GuruHoldingOut(BaseModel):
    symbol: str | None
    cusip: str | None
    name: str
    shares: float
    value_usd: float
    weight_pct: float = Field(description="Share of the snapshot's total value, in percent")


class GuruHoldingsOut(BaseModel):
    guru: GuruOut
    holdings: list[GuruHoldingOut]
    total: int = Field(description="Positions in the snapshot before the `top` cut")


class SyncOut(BaseModel):
    syncing: bool
    gurus: list[GuruOut]


class OverlapOut(BaseModel):
    symbol: str
    name: str
    my_weight_pct: float
    guru_weight_pct: float


class MissingOut(BaseModel):
    symbol: str | None
    name: str
    weight_pct: float


class GuruCompareOut(BaseModel):
    guru: GuruOut
    # My tickers this investor holds, their largest first.
    overlaps: list[OverlapOut]
    # Their ten largest positions that I do not hold.
    top_missing: list[MissingOut]


class CompareOut(BaseModel):
    # True when a first sync was just started in the background; poll again in a few seconds.
    syncing: bool
    gurus: list[GuruCompareOut]
