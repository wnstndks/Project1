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
- 시세 캐시는 `app/services/market_data.py`가 담당한다. 일봉은 `price_bars`에 저장하고, `symbol_syncs`에 받아온 범위를 기록해 없는 날짜만 받는다. 15분이 지나면 마지막 봉부터 다시 받아 진행 중인 봉을 덮어쓴다. 현재가는 메모리 캐시(60초)를 쓴다.
- USD/KRW 환율도 별도 테이블 없이 `price_bars`에 심볼 `KRW=X`로 저장한다.
- `AM_MARKET_PROVIDER=fake`로 실행하면 네트워크 없이 `FakeProvider`의 합성 시세를 쓴다.
- 보유 현황은 저장하지 않고 `transactions`에서 이동평균 단가 방식으로 계산한다(`services/ledger.py`, 순수 함수). 거래를 생성·수정·삭제할 때는 해당 종목의 장부 전체를 다시 계산해, 어느 시점이든 보유량보다 많이 파는 거래가 생기면 거부한다.
- 서비스 계층은 HTTP를 모른다. 규칙 위반은 `services/errors.py`의 `DomainError`(422)·`NotFoundError`(404)로 던지고, `main.py`의 예외 핸들러가 HTTP 응답으로 바꾼다.
- API 응답의 `Decimal` 필드는 `schemas/common.py`의 `Num` 타입으로 선언해 JSON 숫자로 직렬화한다.
- LSTM(`app/ml/`): `features.py`(행 t의 피처는 t까지의 데이터만 사용, 타깃은 t→t+1..5 누적 로그수익률) → `dataset.py`(시간순 train/val/test 분할, 분할 사이에 horizon만큼 퍼지, 스케일러는 train 구간에만 fit) → `train.py`(조기 종료, 테스트 구간 평가) → `artifacts/{symbol}/`에 `model.pt` + JSON(meta, metrics, backtest) 저장(git 제외). 학습은 CLI 또는 `POST /api/predictions/{symbol}/train`(프로세스 내 스레드, 한 번에 하나)으로 실행하고, `GET /api/predictions/{symbol}`은 저장된 모델로 추론만 한다. 로드한 모델은 파일 mtime 기준으로 캐시한다.
- 원화 표시: 장부(`ledger.py`)는 거래마다 해당 거래일의 USD/KRW(`MarketDataService.usd_krw_lookup`, 주말·휴일은 직전 영업일 환율)로 원화 원금과 원화 실현손익을 따로 계산한다. 그래서 `*_krw` 필드는 USD 값 × 오늘 환율과 다르고 환차손익(`fx_pnl_krw`)을 포함한다. 프론트엔드는 `useMoney().pick(usd, krw)`로 두 값 중 하나를 고르며, 원화 값을 직접 다시 계산하지 않는다. 종목 시세처럼 USD만 있는 값은 오늘 환율로 환산한다.
- 장기 전망은 LSTM이 아니라 `services/projection.py`의 몬테카를로 시뮬레이션이 담당한다. 순수 함수 `simulate()`(자산군 2개, 상관된 월간 로그정규 수익률, 월 적립, 리밸런싱 없음, KRW·현재 환율 고정)와 과거 시세로 변동성·상관관계를 추정하는 `ProjectionService`로 나뉜다. 기대수익률 기본값은 보수적 상수(주식 7%, 코인 10%)이고, 과거 평균은 참고값으로만 응답에 포함한다. 보유가 없는 자산군은 SPY/BTC-USD를 대리 지표로 쓴다.
- 프론트엔드는 백엔드 `/api`만 호출한다. API 호출은 `src/api/client.ts`(타입은 생성된 `schema.d.ts`에서 가져옴), React Query 훅은 `src/api/hooks.ts`에 모은다. 거래를 바꾸는 mutation은 `['portfolio']`와 `['transactions']` 쿼리를 모두 무효화한다.
- 거래 입력값(수량·단가·수수료)은 문자열로 보내 백엔드가 정확한 Decimal로 파싱하게 한다.
- 페이지는 `main.tsx`에서 lazy route로 나눠, recharts(대시보드)와 lightweight-charts(종목 상세)가 필요한 페이지에서만 로드된다.
- 색상은 `src/index.css`의 CSS 변수(라이트/다크)로만 쓴다. 차트 시리즈 색은 색각이상 검증을 통과한 팔레트(`--series-1` 파랑, `--series-2` 주황)다. 손익은 한국 관례대로 상승 빨강(`text-gain`), 하락 파랑(`text-loss`)이고 색만으로 구분하지 않도록 부호와 ▲▼를 함께 표시한다. lightweight-charts는 canvas라서 `getComputedStyle`로 변수를 읽어 적용한다.
- 자산 추이의 원화 투자원금(`cost_basis_krw`)은 매수일 환율로 고정된 값이다. 오늘 환율로 다시 환산하지 않는다.

## 도메인 규칙
- 거래 장부의 금액·수량은 `Decimal`이고, DB에는 `DecimalText` 타입(TEXT 저장)으로 넣는다. SQLite의 Numeric은 float로 변환되어 정확도가 깨지기 때문이다. 시세 데이터(`price_bars`)는 float로 둔다.
- 레코드는 원래 통화로 저장(주식·코인 USD)하고 합계는 KRW로 환산한다.
- 모델을 바꾼 뒤 마이그레이션을 생성하면 `alembic check`로 누락이 없는지 확인한다. SQLite라서 `render_as_batch=True`로 설정되어 있다.
- 시계열 누수 금지: 시간순 분할, 셔플 금지, 스케일러는 train에만 fit한다.
- 예측 성능은 항상 기준선(전일 종가 유지)과 함께 보고한다. 예측·시뮬레이션 화면에 투자 조언 아님 고지.
- 시뮬레이션은 seed를 받아 재현 가능해야 한다.

## 공개 저장소 주의
실제 보유 데이터, `*.db`, `.env`, `backend/artifacts/`는 커밋하지 않는다. 데모는 `backend/seed/`의 가짜 데이터를 사용한다.
