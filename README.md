# Asset Manager

미국 주식과 코인(BTC, ETH, XRP, SOL)을 관리하는 개인 자산관리 웹앱입니다. LSTM 단기 가격 예측과 몬테카를로 미래 자산 시뮬레이션을 제공합니다.

> 개발 중입니다. 화면, 실행 방법, 모델 성능은 기능이 완성되는 대로 채웁니다.

## 기능
- 주식·코인 거래 내역 관리와 보유 현황, 수익률 계산 (USD/KRW)
- 자산 대시보드: 총 자산, 손익, 비중, 기간별 추이
- LSTM 기반 단기(5봉) 종가 예측과 기준선 대비 성능 비교
- 몬테카를로 미래 자산 시뮬레이션
- (예정) 부동산 관심 매물 분석

## 기술 스택
- Backend: Python, FastAPI, SQLAlchemy, SQLite, yfinance, PyTorch
- Frontend: React, TypeScript, Vite, TanStack Query, Tailwind CSS

## 면책
이 프로젝트의 예측과 시뮬레이션 결과는 학습·참고용이며 투자 조언이 아닙니다.
