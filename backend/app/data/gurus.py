"""Well-known investors whose public holdings the app compares against.

Two free sources: ARK publishes each ETF's holdings daily (Cathie Wood), and every other
manager here files a quarterly 13F with the SEC (long US positions only, published up to 45
days after quarter end). CIKs were read from EDGAR's company search (2026-10-22 for the first
six filers, 2026-10-23 for the rest), not typed from memory; the latest 13F-HR seen for each is
noted so a wrong CIK shows up. `expected_name` must appear in the filer's EDGAR name (or a
former name) or the sync stops with "CIK 불일치" instead of storing a stranger's portfolio.

Not included: David Einhorn's Greenlight Capital (CIK 0001079114) filed its last 13F-HR on
2024-02-14; Renaissance Technologies (CIK 0001037389) files thousands of positions and waits
for an OpenFIGI key before its tickers can be mapped in reasonable time (DECISIONS.md D-030).
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
    # 13F: upper-case keyword the EDGAR filer name (or a former name) must contain.
    expected_name: str | None = None


GURUS: tuple[Guru, ...] = (
    Guru(
        id="cathie-wood",
        name_ko="캐시 우드 (ARK)",
        name_en="Cathie Wood",
        source="ark",
        funds=("ARKK", "ARKW", "ARKG", "ARKQ", "ARKF", "ARKX"),
        note="ARK 액티브 ETF 6종의 보유를 시가총액 가중으로 합산. ETF 보유이며 개인 계좌가 아님.",
    ),
    Guru(
        id="warren-buffett",
        name_ko="워런 버핏 (버크셔 해서웨이)",
        name_en="Warren Buffett",
        source="13f",
        cik="0001067983",  # BERKSHIRE HATHAWAY INC; latest 13F-HR seen 2026-08-14 (Q2 2026)
        expected_name="BERKSHIRE HATHAWAY",
        note="Berkshire Hathaway의 13F. 보험 자회사 보유를 합산한 미국 상장 롱 포지션.",
    ),
    Guru(
        id="michael-burry",
        name_ko="마이클 버리 (사이언)",
        name_en="Michael Burry",
        source="13f",
        cik="0001649339",  # Scion Asset Management, LLC; latest 13F-HR seen 2025-11-03 (Q3 2025)
        expected_name="SCION ASSET",
        note="Scion Asset Management의 13F. 옵션 포지션은 제외되어 실제 방향과 다를 수 있음.",
    ),
    Guru(
        id="bill-ackman",
        name_ko="빌 애크먼 (퍼싱 스퀘어)",
        name_en="Bill Ackman",
        source="13f",
        cik="0001336528",  # Pershing Square Capital Management, L.P.; latest 13F-HR 2026-05-15
        expected_name="PERSHING SQUARE",
        note="Pershing Square Capital Management의 13F.",
    ),
    Guru(
        id="stanley-druckenmiller",
        name_ko="스탠리 드러켄밀러 (듀케인)",
        name_en="Stanley Druckenmiller",
        source="13f",
        cik="0001536411",  # Duquesne Family Office LLC; latest 13F-HR seen 2026-08-14
        expected_name="DUQUESNE",
        note="Duquesne Family Office의 13F.",
    ),
    Guru(
        id="ray-dalio",
        name_ko="레이 달리오 (브리지워터)",
        name_en="Ray Dalio",
        source="13f",
        cik="0001350694",  # Bridgewater Associates, LP; latest 13F-HR seen 2026-08-14
        expected_name="BRIDGEWATER",
        note="Bridgewater Associates의 13F. 종목이 약 1,000개라 티커 변환이 몇 번에 나눠 진행됨.",
    ),
    Guru(
        id="david-tepper",
        name_ko="데이비드 테퍼 (아팔루사)",
        name_en="David Tepper",
        source="13f",
        # Appaloosa LP (files since 2019). The older "APPALOOSA MANAGEMENT LP" CIK 0001006438
        # stopped filing after Q4 2015.
        cik="0001656456",  # latest 13F-HR seen 2026-08-14
        expected_name="APPALOOSA",
        note="Appaloosa LP의 13F.",
    ),
    Guru(
        id="george-soros",
        name_ko="조지 소로스 (소로스 펀드)",
        name_en="George Soros",
        source="13f",
        cik="0001029160",  # SOROS FUND MANAGEMENT LLC; latest 13F-HR seen 2026-08-14
        expected_name="SOROS FUND",
        note="Soros Fund Management의 13F. 패밀리 오피스이며 옵션·채권은 제외됨.",
    ),
    Guru(
        id="carl-icahn",
        name_ko="칼 아이칸",
        name_en="Carl Icahn",
        source="13f",
        cik="0000921669",  # ICAHN CARL C; latest 13F-HR seen 2026-08-14
        expected_name="ICAHN",
        note="Carl Icahn 개인 명의 13F. 보유 종목이 적고 Icahn Enterprises 비중이 큼.",
    ),
    Guru(
        id="howard-marks",
        name_ko="하워드 막스 (오크트리)",
        name_en="Howard Marks",
        source="13f",
        cik="0000949509",  # OAKTREE CAPITAL MANAGEMENT LP; latest 13F-HR seen 2026-08-14
        expected_name="OAKTREE CAPITAL",
        note="Oaktree Capital Management의 13F. 본업인 채권·사모 투자는 13F에 없음.",
    ),
    Guru(
        id="seth-klarman",
        name_ko="세스 클라먼 (바우포스트)",
        name_en="Seth Klarman",
        source="13f",
        # BAUPOST GROUP LLC/MA. The older "BAUPOST GROUP LLC /ADV" CIK 0001054420 stopped in 2002.
        cik="0001061768",  # latest 13F-HR seen 2026-08-13
        expected_name="BAUPOST",
        note="Baupost Group의 13F. 미국 상장 주식만 보이며 현금·사모 비중은 알 수 없음.",
    ),
    Guru(
        id="li-lu",
        name_ko="리 루 (히말라야 캐피털)",
        name_en="Li Lu",
        source="13f",
        cik="0001709323",  # Himalaya Capital Management LLC; latest 13F-HR seen 2026-08-14
        expected_name="HIMALAYA CAPITAL",
        note="Himalaya Capital의 13F. 종목이 몇 개뿐이고 홍콩 상장 주식은 포함되지 않음.",
    ),
    Guru(
        id="gates-foundation",
        name_ko="게이츠 재단 트러스트",
        name_en="Gates Foundation Trust",
        source="13f",
        # Renamed from "BILL & MELINDA GATES FOUNDATION TRUST" on 2024-11-14.
        cik="0001166559",  # latest 13F-HR seen 2026-08-14
        expected_name="GATES FOUNDATION TRUST",
        note="Gates Foundation Trust의 13F. 재단 기금이며 빌 게이츠 개인 계좌가 아님.",
    ),
    Guru(
        id="mohnish-pabrai",
        name_ko="모니시 파브라이 (달랄 스트리트)",
        name_en="Mohnish Pabrai",
        source="13f",
        cik="0001549575",  # Dalal Street, LLC; latest 13F-HR seen 2026-08-13
        expected_name="DALAL STREET",
        note="Dalal Street의 13F. 미국 상장 종목만 보이며 인도·터키 주식은 포함되지 않음.",
    ),
    Guru(
        id="terry-smith",
        name_ko="테리 스미스 (펀드스미스)",
        name_en="Terry Smith",
        source="13f",
        # Fundsmith LLP (London). Three other "Fundsmith" CIKs file no 13F-HR.
        cik="0001569205",  # latest 13F-HR seen 2026-08-14
        expected_name="FUNDSMITH",
        note="Fundsmith LLP의 13F. 유럽 상장 종목은 포함되지 않음.",
    ),
    Guru(
        id="dan-loeb",
        name_ko="댄 롭 (서드 포인트)",
        name_en="Dan Loeb",
        source="13f",
        cik="0001040273",  # Third Point LLC; latest 13F-HR seen 2026-08-14
        expected_name="THIRD POINT",
        note="Third Point의 13F. 공매도·옵션·채권 포지션은 제외됨.",
    ),
    Guru(
        id="national-pension-service",
        name_ko="국민연금 (NPS)",
        name_en="National Pension Service",
        source="13f",
        cik="0001608046",  # National Pension Service; latest 13F-HR seen 2026-08-13
        expected_name="NATIONAL PENSION SERVICE",
        note="국민연금의 13F. 직접 운용하는 미국 상장 주식만 보이며 위탁 운용분은 빠질 수 있음.",
    ),
    Guru(
        id="norges-bank",
        name_ko="노르웨이 국부펀드 (Norges Bank)",
        name_en="Norges Bank",
        source="13f",
        # Q1 and Q3 tables are filed under confidential treatment (empty) and published a year
        # later as 13F-HR/A; the provider falls back to the latest quarter that has rows.
        cik="0001374170",  # latest 13F-HR seen 2026-08-12
        expected_name="NORGES BANK",
        note="Norges Bank의 13F. 1·3분기 표는 기밀 처리로 비어 있어 직전 분기를 표시할 수 있음.",
    ),
)


def find_guru(guru_id: str) -> Guru | None:
    for g in GURUS:
        if g.id == guru_id:
            return g
    return None
