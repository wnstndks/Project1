from datetime import date, datetime

from pydantic import BaseModel, Field

# Sent with every response so the screen cannot drop the caveats (DECISIONS.md D-030).
COVERAGE_NOTE_KO = (
    "미국 하원 의원의 STOCK Act 거래 공시(PTR)입니다. 거래 뒤 최대 45일 지나 공시되고, "
    "금액은 구간으로만 공개됩니다. 본인·배우자·자녀·공동 계좌 거래가 포함됩니다. "
    "상원은 포함되지 않습니다. 투자 조언이 아닙니다."
)


class CongressTradeOut(BaseModel):
    symbol: str | None
    asset_name: str
    asset_type: str | None = Field(description="Clerk asset code, e.g. ST (stock), MF (fund)")
    member: str
    chamber: str
    state: str
    district: str
    party: str | None = Field(description="Not in the Clerk's data; reserved for a later source")
    owner: str = Field(description="SELF | SP (spouse) | DC (dependent child) | JT (joint)")
    side: str = Field(description="buy | sell | sell_partial | exchange")
    transaction_date: date
    notification_date: date | None
    filing_date: date
    amount_low: int
    amount_high: int | None = Field(description="None for 'Over $X'")
    amount_label: str
    cap_gains_over_200: bool | None
    doc_id: str
    doc_url: str = Field(description="The original PDF on the Clerk's site")


class CongressStatusOut(BaseModel):
    source: str
    synced_at: datetime | None
    index_modified: datetime | None = Field(description="Last-Modified of the Clerk's index")
    # No sync yet, the last one failed, or the last success is older than three days.
    stale: bool
    # A background run is still working through batches; poll again in a few seconds.
    syncing: bool
    error: str | None
    docs_total: int
    docs_parsed: int
    docs_no_text: int = Field(description="Scanned paper filings that cannot be read")
    docs_failed: int
    # 다음 동기화가 처리할 문서(처음 받는 것·실패 재시도·파서 변경 뒤 재파싱) =
    # services.congress.CongressStatus.docs_pending. description은 gen:api 산출물에 들어가므로
    # 그대로 둔다.
    docs_pending: int = Field(description="Still to download; a first sync works in batches")
    trades: int
    coverage_note: str = COVERAGE_NOTE_KO


class CongressTradesOut(BaseModel):
    # True when a first sync was just started in the background; poll again in a few seconds.
    syncing: bool
    status: CongressStatusOut
    trades: list[CongressTradeOut]


class CongressSyncOut(BaseModel):
    syncing: bool
    status: CongressStatusOut
