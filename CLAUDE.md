# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요
개인 자산관리 웹앱: 미국 주식 + 코인 4종(BTC, ETH, XRP, SOL) 보유 관리, LSTM 단기 가격 예측, 몬테카를로 미래 자산 시뮬레이션. 부동산 관심 매물 분석은 주식·코인 기능 이후에 추가한다. 본인 실사용과 공개 취업 포트폴리오를 겸한다.

> 초기 개발 중이다. 단계별 구현 계획은 `~/.claude/plans/rustling-jingling-reddy.md`에 있다. 아래 명령어와 구조 중 아직 만들어지지 않은 부분이 있으면, 해당 단계를 구현할 때 이 파일을 실제와 맞게 갱신한다.

## 명령어 (Windows PowerShell, uv는 `py -m uv`로 실행)
Backend (`backend/`):
- 설치 `py -m uv sync` / 서버 `py -m uv run uvicorn app.main:app --reload` (문서: http://localhost:8000/docs)
- 테스트 `py -m uv run pytest` / 단일 `py -m uv run pytest tests/test_portfolio.py::test_name`
- 린트 `py -m uv run ruff check .` / 포맷 `py -m uv run ruff format .`
- 마이그레이션 `py -m uv run alembic revision --autogenerate -m "msg"` → `py -m uv run alembic upgrade head`
- 모델 학습 `py -m uv run python -m app.ml.train --symbol AAPL`
- 데모 데이터: 실제 DB를 건드리지 않도록 별도 파일을 지정한다. `$env:AM_DATABASE_URL="sqlite:///demo.db"; py -m uv run python -m seed.load` (`--reset`은 모든 거래를 삭제한다)

Frontend (`frontend/`, Vite 8 + React 19 + TS 6, 린트는 ESLint가 아니라 oxlint):
- `npm install` / `npm run dev` (http://localhost:5173, `/api`는 8000번 백엔드로 프록시) / `npm run build` / `npm run lint`
- 테스트 `npm test` / 단일 `npx vitest run src/lib/format.test.ts`
- API 타입 재생성 `npm run gen:api`: 서버 없이 `app.export_openapi`로 `src/api/openapi.json`을 만든 뒤 `src/api/schema.d.ts`를 생성한다. 백엔드 스키마를 바꾸면 반드시 실행하고 두 파일을 함께 커밋한다. openapi-typescript는 TS 5를 요구해 devDependency가 아니라 `npx`로 실행한다.

## 아키텍처
- 라우터(`app/api`) → 서비스(`app/services`) → DB(`app/db`)·시세 공급자(`app/data`). 계산 로직은 서비스에만 둔다.
- yfinance는 `app/data/yfinance_provider.py`에서만 import한다. 주식과 코인(`BTC-USD` 형식) 모두 `MarketDataProvider`를 거친다. 테스트는 `FakeProvider`로 네트워크 없이 돈다.
- 코인은 `app/data/assets.py`의 허용 목록 4종만 받는다. 코인은 365일 거래되므로 거래일을 가정하지 않는다.
- 시세 캐시는 `app/services/market_data.py`가 담당한다. 일봉은 `price_bars`에 저장하고, `symbol_syncs`에 받아온 범위를 기록해 없는 날짜만 받는다. 15분이 지나면 마지막 봉 10일 전부터 다시 받아 진행 중인 봉을 덮어쓴다. 이때 겹치는 구간 앞쪽의 연속된 봉이 같은 비율로 달라졌으면(분할·배당으로 Yahoo가 기준일 이전 가격을 재조정한 경우, `_rescaled`) 전체 기간을 다시 받고, 다시 받은 범위가 기존 캐시를 덮을 때만 교체한다. 중간의 봉 하나만 다르면 그 봉만 덮어쓴다. 받는 도중 캐시가 지워졌으면(새 분할 기록) 부분 구간을 쓰지 않고 전체를 다시 받는다. 네트워크 요청은 DB 쓰기 전에 끝낸다. 현재가는 메모리 캐시(60초)를 쓴다.
- 시장 달력은 `app/data/calendar.py`(exchange_calendars XNYS)에만 둔다. 아직 마감되지 않은 봉(장 마감 전 주식, 당일 UTC 코인)은 `get_history(..., final_only=True)`로 빼고 학습·추론·시뮬레이션에 쓴다. 예측 날짜는 `next_trading_dates`(휴장일 제외), 뉴스 마감 시각은 `us_close_utc`(조기 폐장 반영)를 쓴다.
- 배당·액면분할(`corporate_actions` 테이블, `services/corporate_actions.py`): `GET /api/corporate-actions`가 공급자의 `get_actions`로 이벤트를 감지한다(종목당 6시간 TTL, 병렬 조회, 실패한 종목은 다음 요청에서 재시도). 배당은 배당락일 전날 보유했을 때만 `detected`로 저장하고, 분할은 첫 거래 이후면 보유와 무관하게 저장한다(보유 0이면 장부에 영향이 없으니 바로 `confirmed`). 사용자가 `confirmed`/`ignored`로 정하고, 상태 변경은 **새 상태 기준으로** 장부를 검증한 뒤 저장한다. 장부는 `confirmed` 이벤트만 거래와 같은 타임라인에 넣는다(`ledger.timeline`: 같은 날이면 배당 → 분할 → 거래 순). 분할은 `split_quantity`(비율을 분수로 맞춰 1:30 역분할도 정확히, 소수 8자리), 배당은 수량 × 주당 금액 × (1 − `withholding`)을 `dividends`로 더하고 `total_pnl`에 포함한다. 원천징수율은 기본 15%이고 종목별로 바꾼다(`POST /api/corporate-actions/withholding`, ADR 등). Yahoo는 과거 배당을 이후 분할로 수정해 주므로 `unadjust_dividends`가 당시 주당 금액으로 되돌린다. 공급자 금액이 바뀌면 감지 상태는 갱신하고, 확정된 배당은 다시 `detected`로 돌린다. 새 분할을 저장하면 그 종목의 시세 캐시를 지운다. Yahoo 일봉은 분할 수정 가격이라, 자산 추이(`portfolio.history`)는 무시되지 않은 분할(`split_events`)의 비율을 기준일 이전 종가에 곱해 실제 가격으로 되돌린다. 무시는 "이미 분할 후 수량·가격으로 입력함"을 뜻한다.
- 스크린샷 가져오기 미리보기는 평균단가가 현재가의 0.02~50배를 벗어나면 `invalid`로 표시한다(원화 금액·총액을 단가로 읽은 경우).
- USD/KRW 환율도 별도 테이블 없이 `price_bars`에 심볼 `KRW=X`로 저장한다.
- `AM_MARKET_PROVIDER=fake`로 실행하면 네트워크 없이 `FakeProvider`의 합성 시세를 쓴다.
- 보유 현황은 저장하지 않고 `transactions`에서 이동평균 단가 방식으로 계산한다(`services/ledger.py`, 순수 함수). 거래를 생성·수정·삭제할 때는 해당 종목의 장부 전체를 다시 계산해, 어느 시점이든 보유량보다 많이 파는 거래가 생기면 거부한다.
- 서비스 계층은 HTTP를 모른다. 규칙 위반은 `services/errors.py`의 `DomainError`(422)·`NotFoundError`(404)로 던지고, `main.py`의 예외 핸들러가 HTTP 응답으로 바꾼다.
- API 응답의 `Decimal` 필드는 `schemas/common.py`의 `Num` 타입으로 선언해 JSON 숫자로 직렬화한다.
- LSTM(`app/ml/`): `features.py`(행 t의 피처는 t까지의 데이터만 사용, 타깃은 t→t+1..5 누적 로그수익률) → `dataset.py`(시간순 train/val/test 분할, 분할 사이에 horizon만큼 퍼지, 스케일러는 train 구간에만 fit) → `train.py`(조기 종료, 테스트 구간 평가) → `ml/artifacts.py`가 `artifacts/{symbol}/{run}/`에 `model.pt` + JSON(meta, metrics, backtest)을 새 폴더로 쓰고 `current.json` 포인터를 원자적으로 바꾼다(git 제외). 학습은 CLI 또는 `POST /api/predictions/{symbol}/train`(프로세스 내 스레드, 한 번에 하나)으로 실행하고, `GET /api/predictions/{symbol}`은 저장된 모델로 추론만 한다. 로드한 모델은 `current.json`이 가리키는 run이 바뀔 때만 다시 읽는다.
- 스크린샷 업로드: Anthropic SDK는 `services/screenshot_extractor.py`에서만 import한다(`ClaudeExtractor`, 기본 모델 `claude-opus-5-5`, `beta.messages.parse` 구조화 출력 + `fallbacks="default"`). 흐름은 미리보기(`POST /api/imports/screenshot`, DB에 쓰지 않음) → 사용자가 확인·수정 → 확정(`POST /api/imports/commit`, `TransactionService.create_many`로 전부 성공 또는 전부 실패)이다. 화면에 원화 매입금액이 보이면 실제 매입 환율을 `transactions.fx_rate`에 저장하고, 장부는 이 값을 시장 환율보다 우선한다(`ledger.trade_fx`). 키는 `backend/.env`의 `AM_ANTHROPIC_API_KEY`(`.env.example` 참고)에 둔다. 업로드 이미지 형식은 확장자가 아니라 파일 내용(`sniff_image_type`)으로 판단한다(.png 이름의 JPEG가 흔함). `AM_IMPORT_EXTRACTOR=fake`로 실행하면 API 키 없이 고정된 데모 인식 결과를 쓴다. 테스트는 `get_extractor`를 `FakeExtractor`로 교체한다.
- 거래 통화: `transactions.currency`(USD|KRW). 주식은 USD만 허용하고, 업비트·빗썸에서 산 코인은 KRW로 기록한다. 한 종목(포지션) 안에서 통화를 섞을 수 없다(`MixedCurrencyError`). KRW 코인은 원화 원금이 정확한 값이고 USD는 거래일 환율로 파생한다. 평가는 업비트 원화 시세(`portfolio.quote_symbol` → `KRW-BTC` 등)로 하고, `RoutingProvider`가 `KRW-*` 심볼을 `UpbitProvider`로 보낸다. 환차손익(`fx_pnl_krw`)은 USD 포지션만으로 계산한다. 김치 프리미엄은 `GET /api/market/kimchi`(주말에는 환율이 오래되어 `fx_stale`). 보유량이 0이 되면 다른 통화로 다시 시작할 수 있고, 기존 USD 코인 기록은 `POST /api/transactions/convert-currency`로 거래일 환율에 맞춰 KRW로 일괄 변환한다. 시뮬레이션의 KRW 코인 변동성은 업비트 원화 시계열로 추정한다.
- 원화 표시: 장부(`ledger.py`)는 거래마다 해당 거래일의 USD/KRW(`MarketDataService.usd_krw_lookup`, 주말·휴일은 직전 영업일 환율)로 원화 원금과 원화 실현손익을 따로 계산한다. 그래서 `*_krw` 필드는 USD 값 × 오늘 환율과 다르고 환차손익(`fx_pnl_krw`)을 포함한다. 프론트엔드는 `useMoney().pick(usd, krw)`로 두 값 중 하나를 고르며, 원화 값을 직접 다시 계산하지 않는다. 종목 시세처럼 USD만 있는 값은 오늘 환율로 환산한다.
- 장기 전망은 LSTM이 아니라 `services/projection.py`의 몬테카를로 시뮬레이션이 담당한다. 순수 함수 `simulate()`(자산군 2개, 상관된 월간 로그정규 수익률, 월 적립, 리밸런싱 없음, KRW·현재 환율 고정)와 과거 시세로 변동성·상관관계를 추정하는 `ProjectionService`로 나뉜다. 기대수익률 기본값은 보수적 상수(주식 7%, 코인 10%)이고, 과거 평균은 참고값으로만 응답에 포함한다. 보유가 없는 자산군은 SPY/BTC-USD를 대리 지표로 쓴다.
- 프론트엔드는 백엔드 `/api`만 호출한다. API 호출은 `src/api/client.ts`(타입은 생성된 `schema.d.ts`에서 가져옴), React Query 훅은 `src/api/hooks.ts`에 모은다. 거래를 바꾸는 mutation은 `['portfolio']`, `['transactions']`, `['corporate-actions']` 쿼리를 모두 무효화한다.
- 거래 입력값(수량·단가·수수료)은 문자열로 보내 백엔드가 정확한 Decimal로 파싱하게 한다.
- 페이지는 `main.tsx`에서 lazy route로 나눠, recharts(대시보드)와 lightweight-charts(종목 상세)가 필요한 페이지에서만 로드된다.
- 색상은 `src/index.css`의 CSS 변수(라이트/다크)로만 쓴다. 차트 시리즈 색은 색각이상 검증을 통과한 팔레트(`--series-1` 파랑, `--series-2` 주황)다. 손익은 한국 관례대로 상승 빨강(`text-gain`), 하락 파랑(`text-loss`)이고 색만으로 구분하지 않도록 부호와 ▲▼를 함께 표시한다. lightweight-charts는 canvas라서 `getComputedStyle`로 변수를 읽어 적용한다.
- 자산 추이의 원화 투자원금(`cost_basis_krw`)은 매수일 환율로 고정된 값이다. 오늘 환율로 다시 환산하지 않는다.

## 도메인 규칙
- 거래 장부의 금액·수량은 `Decimal`이고, DB에는 `DecimalText` 타입(TEXT 저장)으로 넣는다. SQLite의 Numeric은 float로 변환되어 정확도가 깨지기 때문이다. 시세 데이터(`price_bars`)는 float로 둔다.
- 레코드는 거래 통화로 저장(주식 USD, 업비트·빗썸 코인 KRW)하고 합계는 KRW로 환산한다.
- 모델을 바꾼 뒤 마이그레이션을 생성하면 `alembic check`로 누락이 없는지 확인한다. SQLite라서 `render_as_batch=True`로 설정되어 있다.
- 시계열 누수 금지: 시간순 분할, 셔플 금지, 스케일러는 train에만 fit한다.
- 예측 성능은 항상 기준선(전일 종가 유지)과 함께 보고한다. 예측·시뮬레이션 화면에 투자 조언 아님 고지.
- 시뮬레이션은 seed를 받아 재현 가능해야 한다.

## 공개 저장소 주의
실제 보유 데이터, `*.db`, `.env`, `backend/artifacts/`는 커밋하지 않는다. 데모는 `backend/seed/`의 가짜 데이터를 사용한다.
