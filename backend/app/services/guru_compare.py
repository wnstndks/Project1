"""My holdings against well-known investors' public snapshots.

Joins `PortfolioService.holdings()` (my weights, percent of market value) with the stored
guru snapshots (`GuruService`, weights 0..1): which of my tickers each investor holds, and
which of their ten largest positions I do not. Pure `compare()` does the join; the service
only loads the inputs. Nothing here fetches: syncing is the router's background job.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.data.guru_provider import GuruHolding
from app.services.gurus import SEC_UA_MISSING, GuruService, GuruStatus
from app.services.portfolio import Holding, PortfolioService

TOP_N = 10


@dataclass(frozen=True)
class OverlapRow:
    symbol: str
    name: str
    my_weight_pct: float
    guru_weight_pct: float


@dataclass(frozen=True)
class MissingRow:
    # None when the CUSIP has not been mapped to a ticker yet; the name still identifies it.
    symbol: str | None
    name: str
    weight_pct: float


@dataclass(frozen=True)
class GuruComparison:
    status: GuruStatus
    overlaps: list[OverlapRow]
    top_missing: list[MissingRow]


def compare(
    statuses: Iterable[GuruStatus],
    holdings_by_guru: dict[str, list[GuruHolding]],
    mine: Iterable[Holding],
) -> list[GuruComparison]:
    """Per investor: my tickers they hold (their largest first) and their top-10 I lack.

    Rows are summed by ticker in case a snapshot lists one issuer twice (share classes).
    """
    my_weight = {h.symbol.upper(): float(h.weight) for h in mine}
    out = []
    for status in statuses:
        rows = holdings_by_guru.get(status.guru.id, [])
        by_symbol: dict[str, tuple[str, float, float]] = {}
        for h in sorted(rows, key=lambda h: h.value_usd, reverse=True):
            if h.symbol is None:
                continue
            key = h.symbol.upper()
            name, value, weight = by_symbol.get(key, (h.name, 0.0, 0.0))
            by_symbol[key] = (name, value + h.value_usd, weight + h.weight)
        ranked = sorted(by_symbol.items(), key=lambda kv: kv[1][1], reverse=True)
        overlaps = [
            OverlapRow(sym, name, round(my_weight[sym], 2), round(weight * 100, 2))
            for sym, (name, _value, weight) in ranked
            if sym in my_weight
        ]
        # Unmapped CUSIPs stay in the ranking (they may be large) but cannot match my tickers.
        top = sorted(rows, key=lambda h: h.value_usd, reverse=True)[:TOP_N]
        missing = [
            MissingRow(h.symbol, h.name, round(h.weight * 100, 2))
            for h in top
            if h.symbol is None or h.symbol.upper() not in my_weight
        ]
        out.append(GuruComparison(status, overlaps, missing))
    return out


def needs_sync(statuses: Iterable[GuruStatus]) -> bool:
    """True while some fetchable investor has never been synced (first visit)."""
    return any(s.synced_at is None and s.error != SEC_UA_MISSING for s in statuses)


class GuruCompareService:
    def __init__(self, gurus: GuruService, portfolio: PortfolioService) -> None:
        self.gurus = gurus
        self.portfolio = portfolio

    def statuses(self) -> list[GuruStatus]:
        return self.gurus.list_all()

    def compare(self, statuses: list[GuruStatus] | None = None) -> list[GuruComparison]:
        statuses = self.statuses() if statuses is None else statuses
        holdings = {s.guru.id: self.gurus.holdings(s.guru.id) for s in statuses if s.holdings_count}
        return compare(statuses, holdings, self.portfolio.holdings())
