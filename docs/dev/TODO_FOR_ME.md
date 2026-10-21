# TODO_FOR_ME

사용자가 직접 결정하거나 실행해야 하는 일이다. 팀은 아래 항목을 대신 처리하지 않는다. 결정이 나기 전까지는 괄호 안의 임시 운영 방식을 따른다.

## 결정이 필요한 일
- [ ] CLAUDE.md의 Kaggle `[대회명]` 확정
  - 현재: G-Research Crypto Forecasting(2021-22) 1위 방식을 일봉으로 이식해 운영 중이다(DECISIONS.md D-001).
  - 대안: JPX Tokyo(2022). M6로 바꾸려면 "Kaggle" 문구도 바꿔야 한다.
- [ ] CLAUDE.md의 MDD `[20]`% 확정
  - 현재: 20%를 확정값으로 쓰고, 설정으로는 더 엄격하게만 바꿀 수 있다(D-002).
  - 일일 손실 3%, 1회 주문 5%, 종목 비중 20% 기본값도 함께 확인한다.
- [ ] `.claude/agents/` 역할 정의를 커밋할지 결정(ISSUE-026)
  - 지금 `.gitignore` 마지막 줄의 `.claude`가 디렉터리 전체를 무시해서 역할 정의가 저장소에 들어가지 않는다. 새로 클론한 팀은 역할 정의 없이 시작하게 된다.
  - 커밋하려면 그 줄을 `.claude/*`와 `!.claude/agents/` 두 줄로 바꾸고, 파일 마지막에 줄바꿈을 넣는다. 지금은 줄바꿈이 없어서 `>>`로 덧붙이면 규칙이 한 줄로 붙어 깨진다.
- [ ] 세금 가정 중 "확인 필요" 항목 확인
  - 코인 과세 시행일. 초안은 2027-01-01, 22%, 연 250만원 공제, 주식과 별도로 통산한다. 시행 여부와 시점은 바뀔 수 있다.
  - 해외주식 양도소득세의 취득가액 산정 방식. 선입선출이 원칙으로 알려져 있지만, 앱 장부(`ledger.py`)는 이동평균이다.
  - 양도차익의 원화 환산 기준일. 실제로는 결제일 기준환율이지만, 백테스트는 거래일 환율로 단순화할 예정이다.
- [ ] (선택) 실제로 쓰는 증권사·거래소의 수수료율과 환전 우대율 확인
  - 백테스트 초안은 미국 주식 편도 0.25%, 환전 0.1%, 업비트 0.05%다.
  - 비율만 알려 주면 되고, 계좌 정보는 필요 없다.

- [ ] 다음 전략 가설 선택(S1 기각 후, PROGRESS.md 3단계 보고)
  - H-a: 생존 편향 없는 과거 구성종목으로 주식 횡단면 넓히기(데이터 확보 필요)
  - H-b: 예측 변동성으로 SPY·BTC 노출을 조절해 MDD 20% 지키기(S2 계열)
  - H-c: 회전율이 낮은 월 단위 이상 규칙
  - H-d: 코인은 자산군 단위 노출 관리로만 다루기
  - 고른 가설은 quant-researcher가 결과를 보기 전에 STRATEGIES.md에 등록하고, `STRATEGY_CONFIGS_TRIED`를 올린다.
- [ ] app-engineer 투입 여부 결정. 아래 항목은 app-engineer 담당 파일이라 다른 역할이 고칠 수 없다.
  - `services/forecasts.py:114`: 참조 종목 순위 피처의 peers를 run의 학습 유니버스로 제한
  - `services/forecasts.py:283`: 환율 대체 경로가 엄격 로더를 쓰도록 변경(D-011, ISSUE-022)
  - `services/forecasts.py:426`: 앱 안의 재학습이 홀드아웃 열람을 기록 없이 함(ISSUE-005)
  - 화면이 새 report 키(`stock:direction` 등)를 읽도록 변경. 그 전까지 화면 edge는 모두 False다.
  - 킬스위치 리셋 API(지금은 사용자만 리셋할 수 있고, 리셋할 화면·API가 없음)
- [ ] CLAUDE.md 갱신 검토. 2단계에서 바뀐 아래 내용이 CLAUDE.md에 아직 없다. 검토 후 반영 여부를 정한다.
  - 확정 봉 판정이 `symbol_syncs.synced_at`(UTC) 기준으로 바뀌었다(D-016).
  - 모의투자 CLI(`python -m app.strategy.paper run|fill|score`)가 생겼다.
  - 새 설정이 생겼다: `AM_RISK_*`, `AM_STRATEGY_BUDGET_*`, `AM_PAPER_INITIAL_CAPITAL_KRW`, `AM_LIVE_TRADING`.
  - 새 테이블이 생겼다: `paper_signals`, `kill_switch_events`.
  - `app/strategy/` 구조: signals, s1, risk, execution, paper, backtest, baselines, evaluation, assess.

## 직접 실행해야 하는 일
- [ ] 모의투자 일일 실행 예약(작업 스케줄러 등). 실제 주문은 나가지 않는다(`AM_LIVE_TRADING`=false).
  - 주식: 금요일 미국 장 마감 뒤(한국 시간 토요일 아침)에 `py -3.11 -m uv run python -m app.strategy.paper run`
  - 코인: 월요일 09:00 KST 뒤(일요일 UTC 봉 마감 뒤)에 같은 `run`
  - 매일 한 번 `... paper fill`(다음 봉 시가 체결)과 `... paper score`(목표일이 지난 신호 채점)
  - 실행 위치는 `backend/`다. 기록은 다음 결정일부터 쌓인다. S1이 기각되어 지금은 모든 신호가 '우위 없음'으로 기록된다.
- [ ] 셸 환경 확인(ISSUE-032)
  - 셸에 `VIRTUAL_ENV`가 `backend\.venv`로 잡혀 있으면 `py -m uv ...`가 `No module named uv`로 실패한다.
  - `py -3.11 -m uv ...`를 쓰거나, PowerShell에서 `Remove-Item Env:VIRTUAL_ENV`로 해제한 뒤 실행한다.
- [ ] (선택) 기준선 ② 원 데이터 재현
  - G-Research 원 분봉 데이터로 1위 점수를 재현하려면(D-001의 A단계) Kaggle API 토큰을 발급하고 대회 규정에 동의해야 한다.
  - 대회 데이터는 라이선스 때문에 저장소에 커밋하지 않는다.

## 알아 둘 일
- 실매매(`AM_LIVE_TRADING`)는 기본값이 `false`이고, 사용자만 켤 수 있다. 코드나 에이전트는 이 값을 바꾸지 않는다. 그 전까지는 모의투자 기록만 남는다.
- 모의투자는 실제 거래 장부(`transactions`)와 분리된 별도 테이블에 기록된다(D-009). 가상 원금은 설정값이다.
- CLAUDE.md는 전략 설정을 바꿀 때 `CONFIGS_TRIED`를 올리라고 적고 있다. 팀은 이를 "예측 모델 설정은 `CONFIGS_TRIED`, 전략 설정은 `STRATEGY_CONFIGS_TRIED`로 따로 센다"로 해석해 운영한다(D-004). 이 해석에 동의하지 않으면 CLAUDE.md 문구를 바꾸거나 알려 주면 된다.
- 전략은 백테스트 관문(D-015 ①)을 통과해도 "후보"일 뿐이다. 이미 열람한 홀드아웃은 참고로만 보고한다. 사전 등록한 26주 전진 모의투자까지 통과해야 "채택"이고, 그 전까지 화면에는 '우위 없음'과 그 이유가 표시된다.
