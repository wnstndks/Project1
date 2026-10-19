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
- 데모 데이터 `py -m uv run python -m seed.load`

Frontend (`frontend/`):
- `npm install` / `npm run dev` / `npm run build` / `npm run lint`
- 단일 테스트 `npx vitest run src/path/to/file.test.ts`
- API 타입 재생성 `npm run gen:api` (백엔드 실행 중이어야 함)

## 아키텍처
- 라우터(`app/api`) → 서비스(`app/services`) → DB(`app/db`)·시세 공급자(`app/data`). 계산 로직은 서비스에만 둔다.
- yfinance는 `app/data/yfinance_provider.py`에서만 import한다. 주식과 코인(`BTC-USD` 형식) 모두 `MarketDataProvider`를 거친다. 테스트는 `FakeProvider`로 네트워크 없이 돈다.
- 코인은 `app/data/assets.py`의 허용 목록 4종만 받는다. 코인은 365일 거래되므로 거래일을 가정하지 않는다.
- 일봉은 `price_bars`에 캐시하고 없는 날짜만 증분으로 받아온다.
- 보유 현황은 저장하지 않고 `transactions`에서 이동평균 단가 방식으로 계산한다.
- LSTM 학습은 CLI로만 하고 결과는 `backend/artifacts/{symbol}/`에 저장한다(git 제외). API는 추론만 한다.
- 장기 전망은 LSTM이 아니라 `services/projection.py`의 몬테카를로 시뮬레이션이 담당한다.
- 프론트엔드는 백엔드 `/api`만 호출하고, OpenAPI에서 생성한 타입 파일은 직접 수정하지 않는다.

## 도메인 규칙
- 금액·수량은 `Decimal` / `Numeric`. 레코드는 원래 통화로 저장(주식·코인 USD)하고 합계는 KRW로 환산한다(USD/KRW는 yfinance `KRW=X`).
- 시계열 누수 금지: 시간순 분할, 셔플 금지, 스케일러는 train에만 fit한다.
- 예측 성능은 항상 기준선(전일 종가 유지)과 함께 보고한다. 예측·시뮬레이션 화면에 투자 조언 아님 고지.
- 시뮬레이션은 seed를 받아 재현 가능해야 한다.

## 공개 저장소 주의
실제 보유 데이터, `*.db`, `.env`, `backend/artifacts/`는 커밋하지 않는다. 데모는 `backend/seed/`의 가짜 데이터를 사용한다.
