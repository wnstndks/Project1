"""Well-known investors whose public holdings the app compares against.

Two free sources: ARK publishes each ETF's holdings daily (Cathie Wood), and every other
manager here files a quarterly 13F with the SEC (long US positions only, published up to 45
days after quarter end). CIKs were checked against EDGAR's full-text search on 2026-10-22,
not typed from memory; the latest 13F-HR seen for each is noted so a wrong CIK shows up.
"""

from dataclasses import dataclass
from typing import Literal

Source = Literal["ark", "13f"]


@dataclass(frozen=True)
class Guru:
    id: str
    name_ko: str
    name_en: str
    source: Source
    # ARK: fund tickers whose holdings are combined. 13F: the filer's 10-digit CIK.
    funds: tuple[str, ...] | None = None
    cik: str | None = None
    note: str = ""


GURUS: tuple[Guru, ...] = (
    Guru(
        id="cathie-wood",
        name_ko="캐시 우드",
        name_en="Cathie Wood",
        source="ark",
        funds=("ARKK", "ARKW", "ARKG", "ARKQ", "ARKF", "ARKX"),
        note="ARK 액티브 ETF 6종의 보유를 시가총액 가중으로 합산. ETF 보유이며 개인 계좌가 아님.",
    ),
    Guru(
        id="warren-buffett",
        name_ko="워런 버핏",
        name_en="Warren Buffett",
        source="13f",
        cik="0001067983",  # BERKSHIRE HATHAWAY INC; latest 13F-HR seen 2026-08-14 (Q2 2026)
        note="Berkshire Hathaway의 13F. 보험 자회사 보유를 합산한 미국 상장 롱 포지션.",
    ),
    Guru(
        id="michael-burry",
        name_ko="마이클 버리",
        name_en="Michael Burry",
        source="13f",
        cik="0001649339",  # Scion Asset Management, LLC; latest 13F-HR seen 2025-11-03 (Q3 2025)
        note="Scion Asset Management의 13F. 옵션 포지션은 제외되어 실제 방향과 다를 수 있음.",
    ),
    Guru(
        id="bill-ackman",
        name_ko="빌 애크먼",
        name_en="Bill Ackman",
        source="13f",
        cik="0001336528",  # Pershing Square Capital Management, L.P.; latest 13F-HR 2026-05-15
        note="Pershing Square Capital Management의 13F.",
    ),
    Guru(
        id="stanley-druckenmiller",
        name_ko="스탠리 드러켄밀러",
        name_en="Stanley Druckenmiller",
        source="13f",
        cik="0001536411",  # Duquesne Family Office LLC; latest 13F-HR seen 2026-08-14
        note="Duquesne Family Office의 13F.",
    ),
    Guru(
        id="ray-dalio",
        name_ko="레이 달리오",
        name_en="Ray Dalio",
        source="13f",
        cik="0001350694",  # Bridgewater Associates, LP; latest 13F-HR seen 2026-08-14
        note="Bridgewater Associates의 13F. 종목이 약 1,000개라 티커 변환이 몇 번에 나눠 진행됨.",
    ),
    Guru(
        id="david-tepper",
        name_ko="데이비드 테퍼",
        name_en="David Tepper",
        source="13f",
        # Appaloosa LP (files since 2019). The older "APPALOOSA MANAGEMENT LP" CIK 0001006438
        # stopped filing after Q4 2015.
        cik="0001656456",  # latest 13F-HR seen 2026-08-14
        note="Appaloosa LP의 13F.",
    ),
)


def find_guru(guru_id: str) -> Guru | None:
    for g in GURUS:
        if g.id == guru_id:
            return g
    return None
