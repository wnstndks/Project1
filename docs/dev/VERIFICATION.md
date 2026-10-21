# VERIFICATION

verifier가 각 작업을 재현하고 반박을 시도한 기록이다. 반박하지 못한 것만 통과시킨다. 공개 저장소이므로 실제 보유 종목·수량·금액은 적지 않는다.

## 1단계 진단 (2026-10-20)

- 판정: **통과**(재확인 2026-10-20, 아래 「1단계 재확인」). 최초 판정은 조건부 통과였다.
  - 치명·높음 이슈 12건은 모두 재현하거나 코드로 확인했다. 완전히 반박된 이슈는 없다.
  - 다만 ISSUE-002와 ISSUE-010의 원인 서술은 이미 사실과 달라졌다(Yahoo 누락이 일시적이었음).
  - DECISIONS.md D-005와 D-006은 문구대로 구현하면 edge 기준이 실질적으로 완화될 수 있다.
  - 아래 「통과 조건」을 반영하면 통과로 바꾼다.
- 대상: `docs/dev/ISSUES.md`(33건), `PROGRESS.md`, `DECISIONS.md`(D-001~D-012), `TODO_FOR_ME.md`, 원 보고서 4개(scratchpad `phase1\{data,quant,eval,risk}.md`), 재현 스크립트 6개
- 기준: 커밋 c8216b6(브랜치 agent-team). 작업 트리에는 `docs/dev/` 말고 변경이 없다.
- 실행 환경: 셸에 `VIRTUAL_ENV`가 잡혀 있어서 모두 `py -3.11 -m uv`로 실행했다(ISSUE-032 재현).

### 통과 조건
1. D-005, D-006 보완(아래 문서 수정 요청 10, 11)
2. 담당자 없는 파일의 담당 지정(요청 9)
3. ISSUE-002, 010의 원인·영향 갱신(요청 1, 2)

### 확인한 항목

| 항목 | 결과 | 근거 |
|---|---|---|
| backend pytest | 165 passed(42초) | `py -3.11 -m uv run pytest` |
| test_forecast.py | 10개 수집 | `pytest --co tests/test_forecast.py` |
| ruff check / format --check | 통과 / 90 files already formatted | |
| frontend npm test | 파일 4개, 테스트 11개 통과 | vitest 5.0.5 |
| PROGRESS edge 표 | 18개 수치 전부 report.json과 일치. Holm m=6, configs_tried=2, IC·t 6쌍, 행 수, 이전 run의 DM −4.9~−6.2까지 일치 | `runs/20261020T135115-4514d73e/report.json`, `20261020T112557-1629e5bb/report.json` |
| PROGRESS 이슈 집계 | 치명 2, 높음 10, 중간 14, 낮음 7. 미해결 29, 보류 4 | ISSUES.md 상태 표 |
| 확정 봉 깨짐(ISSUE-001) | 재현됨 | `repro_partial.py`를 읽고 실행했다. 합성 공급자를 썼지만 실제 `MarketDataService`를 지난다 |
| demo.db 코인 10-19 봉(ISSUE-002) | 수치 일치. Yahoo 확정값으로 미완성이었음을 확인 | 아래 반박·수정 1 |
| 학습·추론 피처 불일치(ISSUE-003) | 확인 | meta의 universe에 FALLEN_COINS 0종, oos에 `*_raw` 열 없음, c8216b6 diff, run 13:51 KST < 커밋 15:31 KST |
| OOS 보유 종목만 저장(ISSUE-004) | 확인 | 세 oos 파일의 종목 수 = meta의 held 수. report 점수는 유니버스 전체 OOS로 계산됨 |
| config_hash에 하이퍼파라미터 없음(ISSUE-007) | 확인 | `train.py:46-48`, 두 run 해시 06aea83d5b7d |
| 홀드아웃 시작일 이동(ISSUE-005) | 확인 | `cv.py:35-36` |
| 같은 봉 체결 위험(ISSUE-006) | 확인(잠재 위험) | `panel.py:145`, oos에 open 없음. 백테스트 코드는 아직 없음 |
| 중간·낮음 이슈의 file:line | 21건 모두 인용 내용과 일치. 높음 이슈 중에서는 ISSUE-007의 `models.py:135`만 어긋남(요청 4) | |
| 원 보고서 ↔ ISSUES 대조 | 원 보고서 항목 45개(data 10, quant 12, eval 13, risk 10)가 모두 이슈 또는 결정에 반영됐다. 근거 없이 추가된 이슈는 없다. 빠진 것은 아래 요청 12, 13 | |
| DECISIONS 규칙 완화 여부 | MDD 완화 없음(D-002는 0 < x ≤ 0.20). 실매매 기본값 변경 없음. edge 기준은 D-005·D-006 문구가 불완전함(요청 10, 11) | |
| `AM_LIVE_TRADING` | 저장소 전체(.venv, node_modules 제외)에 `live_trading=true` 패턴 0건. `backend/.env`에 LIVE 키 없음 | grep |
| 공개 저장소 | 문서에서 held 목록과 일치하는 종목명은 모두 기준선(SPY·BTC 단순 보유) 또는 앱이 지원하는 코인 4종의 시세 표로만 나온다. 사용자 보유를 밝히는 문맥은 없다. 간접 노출 2곳은 요청 1, 14 | meta.json held와 대조, 종목명 비공개 |

### 재현 명령
backend 디렉터리에서 실행한다. `SP`는 scratchpad 경로 `C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Desktop-project\36e33b77-5e46-45ef-aae5-8694a7ac64f1\scratchpad`다.
```
py -3.11 -m uv run pytest ; py -3.11 -m uv run ruff check . ; py -3.11 -m uv run ruff format --check .
(frontend) npm test
PYTHONPATH=. py -3.11 -m uv run python $SP/repro_partial.py      # ISSUE-001
PYTHONPATH=. py -3.11 -m uv run python $SP/gap.py                # ISSUE-002, 010 (네트워크 3건)
PYTHONPATH=. py -3.11 -m uv run python $SP/fallen.py             # ISSUE-003 (네트워크 10건)
PYTHONPATH=. py -3.11 -m uv run python $SP/drill.py demo.db      # ISSUE-021, 023
PYTHONPATH=. py -3.11 -m uv run python $SP/verifier/empty_refresh.py   # ISSUE-022
```
- DB는 모두 `file:...?mode=ro`로 열었다. 실제 DB에서는 `symbol_syncs`, `price_bars`만 읽고 `transactions`는 열지 않았다.
- ISSUE-017 MDD, ISSUE-018·019 분포, report.json 대조는 일회성 `python -c`로 계산했다(위 표의 수치).

### 반박·수정된 주장
1. ISSUE-002 원인 "지금 Yahoo가 10-19 코인 봉을 주지 않는다": 일시적이었다.
   - 2026-10-20 07:36 UTC에 `gap.py`를 다시 돌리니 BTC/BNB/ADA 모두 10-19를 반환했다. BTC 10-19 확정 종가는 81,853.54로, 캐시 82,800.32보다 1.16% 낮고 10-20 시가 81,844.43과 이어진다. 그래서 캐시 봉이 미완성이었다는 주장은 오히려 더 강해졌다.
   - 대신 캐시는 다음 stale 동기화에서 스스로 고쳐진다. 마지막 봉 10일 전부터 다시 받아 upsert하기 때문이다(`market_data.py:177-189`). `_rescaled`는 겹치는 구간의 마지막 봉 하나만 달라서 발동하지 않는다.
   - 영구히 남는 영향은 이미 학습된 run과 그 시점에 보여 준 예측이다.
   - `forecast_log.base_price`는 저장만 되고 채점에 쓰이지 않는다. 채점은 `forecasts.py:154-180`에서 캐시 adj_close를 다시 읽는다. 따라서 "base_price가 미완성 봉 기준"은 사실이지만 영향은 없다.
2. ISSUE-002 심각도 "치명": 과장 소지가 있다.
   - 영향 범위는 코인당 피처 1행과 기간별 타깃 1행(1d 10-18, 1w 10-12, 1m 09-19 행)이다. 전체 패널 행 중 극히 일부이고 캐시는 스스로 고쳐진다.
   - 메커니즘(ISSUE-001)이 치명인 것은 맞다. ISSUE-002는 높음으로 낮추는 것을 제안한다. 리드가 판단한다.
3. ISSUE-010 원인(가설, Yahoo 누락): 일시적 누락이라는 쪽의 근거가 생겼다.
   - FALLEN_COINS 10종도 지금은 10-19까지 온다(봉 수 1,989~3,267).
   - 봉 순번 shift 문제는 그대로 유효하다.
4. ISSUE-017 "수치는 기억 기반, 가설": 데이터로 확인했다. adj_close 기준으로 SPY는 −33.7%(2020-03-23)와 2021~22년 −24.5%, BTC는 −83.4%(2018-12-15)와 2021~22년 −76.6%다.
5. ISSUE-022 가설 "빈 응답이면 `synced_at`이 갱신될 수 있다": 코드 경로를 재현했다. 기존 sync가 있고 TTL이 지난 상태에서 공급자가 `[]`를 주면 `synced_at`이 앞으로 간다. yfinance가 실제로 빈 DataFrame을 주는지는 미확인이다.

### 발견한 문제(코드, 담당자에게 전달)
- V-1(ISSUE-003 확장, quant-researcher): 추론 때 `load_inputs`가 `reference_symbols()`로 FALLEN_COINS 10종을 불러온다. 그러면 `latest_ranks`(`panel.py:233-259`)의 코인 순위 피처 비교군이 학습 때 15종에서 최대 25종으로 바뀐다. 즉 dxy 지연 말고도 현재 run에는 추론 피처 분포 불일치가 하나 더 있다. 재학습으로 함께 해소된다.
- V-2(ISSUE-022 일부 확인, data-engineer): 빈 갱신 응답에도 `synced_at`이 갱신된다(재현 `scratchpad\verifier\empty_refresh.py`). ISSUE-001과 겹치면 미완성 봉의 수명이 늘어난다.
- V-3(리드): 담당자가 없는 파일이 이슈 해결 경로에 들어 있다. 상세는 요청 9.

### 문서 수정 요청
1. ISSUE-002
   - 원인을 위 반박·수정 1로 갱신한다(일시적 누락, 캐시는 스스로 고쳐짐, 영구 영향은 run과 표시된 예측).
   - `forecast_log.base_price`는 채점에 쓰이지 않는다고 적는다.
   - 영향받은 1w·1m 타깃 행도 적는다.
   - 심각도를 다시 판단한다.
   - "이 네 코인의 `forecast_log.base_price`" 문장은 forecast_log가 보유 종목만 기록한다는 점과 합쳐져 보유 여부를 간접적으로 드러낸다. 코인 이름 없이 다시 쓴다.
2. ISSUE-010과 PROGRESS 데이터 표
   - 10-19가 없는 코인은 AVAX를 포함해 11종이다.
   - AVAX 2020년 결측은 69일(2020-07-15~09-21)이다. 10-19까지 합쳐야 70일이다.
   - PROGRESS 표의 "기타 COINS 10종 / 각 1"은 "11종 / AVAX만 70"으로 고친다.
   - "FALLEN_COINS는 10-18까지만 온다"와 원인 가설은 07:36 UTC 재요청 결과로 갱신한다.
3. ISSUE-003: 불일치 목록에 V-1(추론 순위 비교군)을 추가하고, 근거에 "디스크 run oos에 `*_raw` 열 없음"을 추가한다.
4. ISSUE-007: 근거 `models.py:135`는 sklearn 학습률이다. 조기 종료 근거는 `models.py:92-93,151-162`다.
5. ISSUE-017: 원인의 "가설(기억 기반)"을 확인된 수치(반박·수정 4)로 바꾼다.
6. ISSUE-018, 019: 수치가 보유 종목만 담긴 oos 파일에서 나왔다고 명시한다(ISSUE-004 때문에 유니버스 전체가 아님). D-008의 1d 제외 근거도 같은 표본이다. 자기상관은 "종목별 계산 후 평균"이라고 계산 방식을 적는다(평균 0.63/0.89/0.93은 재현됨).
7. ISSUE-022: 원인의 가설 중 코드 경로 부분은 확인됐다고 적고, 남은 가설은 yfinance 동작으로 좁힌다.
8. ISSUE-023: "2% 넘게 움직인 15일은 모두 실제 사건일과 일치"는 근거가 없다. 확인한 날짜만 적거나 "미확인"으로 표시한다.
9. 담당 파일 공백: 다음 파일은 `.claude/agents/` 어느 역할에도 없는데, 이슈 해결 경로에 들어 있다. DECISIONS.md에 담당을 지정한다.
   - `backend/app/forecast/data.py`: ISSUE-022에서 quant-researcher에게 배정됨
   - `forecast/universe.py`: ISSUE-003의 XMR·ZEC 판단, ISSUE-024의 지연 변경
   - `forecast/store.py`: ISSUE-004·D-010의 별도 OOS 저장
   - `forecast/metrics.py`: ISSUE-009의 검정 추가
   - `forecast/aggregate.py`
   - `tests/conftest.py`
10. D-005: 자산군(주식/코인)으로 나누면 비교 수가 2배가 된다. 그만큼 Holm의 m도 늘린다는 문장을 넣는다. 없으면 같은 검정에 기회를 두 번 주는 완화가 된다.
11. D-006: 순위 정보(IC) 비교의 홀드아웃 관문을 어떻게 처리할지 명시한다.
    - 홀드아웃 IC(t 2.74/2.99/2.34)는 이미 열람했고, 통과한다는 것도 알려져 있다. 이를 관문으로 세면 실질적 완화가 된다.
    - "전진 모의투자 확인 전까지 IC 기반 edge는 False('우위 없음')"로 정하거나, 이와 같은 수준의 규칙을 적는다.
12. 전략 채택 규칙 사전 등록 누락: quant A8(변동성을 맞춘 기준선 대비 순 Sharpe)과 eval E-4(예측 edge AND 초과수익 검정 AND 연도 일관성 AND 홀드아웃 1회 AND MDD ≤ 20%)의 채택 조건이 DECISIONS.md에 없다.
    - 2단계 결과를 보기 전에 등록해야 한다.
    - E-4 초안의 "홀드아웃 1회" 조건은 D-007(홀드아웃 오염, 전진 모의투자로 확인)과 충돌하므로 함께 정리한다.
13. D-004: CLAUDE.md는 전략 설정 변경 때 `CONFIGS_TRIED`를 올리라고 적고 있다. 별도 카운터 `STRATEGY_CONFIGS_TRIED`는 그 문구와 다르다. 근거는 D-004에 있지만 CLAUDE.md 문구를 바꾸는 해석이므로 TODO_FOR_ME.md 「알아 둘 일」에 한 줄 남긴다.
14. 공개 정보 최소화: 보유 종목 수를 역산할 수 있는 수치를 본문에서 뺀다. ISSUE-003 본문의 유니버스 총수, 패널·OOS 행 수(ISSUE-002, 004, PROGRESS), 실제 DB 캐시 종목 수가 여기에 해당한다. "FALLEN_COINS 0종", "전체 패널 중 극히 일부"처럼 쓴다. verifier가 쓴 검증 줄과 이 문서에서는 이미 지웠다.
15. D-011: `forecasts.py:283`의 `final_only` 누락은 app-engineer 투입 시점이 정해지지 않아 기한 없이 남는다. "모의투자 기록 시작 전 처리" 같은 기한을 적는다.
16. ISSUES.md 범례 13행("모두 verifier가 아직 확인하지 않았다")과 PROGRESS.md 54행("모두 verifier 미확인")은 이번 검증으로 사실이 아니게 됐다. 갱신한다. verifier는 검증 줄만 고칠 수 있어서 직접 바꾸지 않았다.

### 1단계 재확인 (2026-10-20, eval의 문서 수정 반영 후)
- 판정: **통과**. 통과 조건 1~4와 문서 수정 요청 16건이 모두 반영됐다. 리드가 확정한 최종 상태(DECISIONS 17:24, ISSUES·PROGRESS·TODO 17:36~17:41)를 다시 대조했다. 남은 R-3, R-4는 서술을 다듬는 선택 사항이고 판정에 영향이 없다.
- 통과 조건
  1. D-005: 자산군 분할로 Holm m이 6에서 12로 늘고, 시점 기준 edge도 같은 m과 `CONFIGS_TRIED` 보정을 쓴다. 반영됐다.
  2. D-006: 홀드아웃 IC를 관문으로 세지 않고, 전진 모의투자 전까지 IC edge는 False다. 백테스트는 walk_forward 안의 시점 기준 IC edge만 쓴다. 반영됐다.
  3. D-013: `forecast/data.py`, `universe.py`, `store.py`, `aggregate.py`, `metrics.py`, `conftest.py`, `db/models.py`, `config.py`, `services/forecasts.py`의 담당이 정해졌다. ISSUE-022의 담당 표기(data-engineer)도 D-013과 맞는다. 반영됐다.
  4. ISSUE-002, 010: 원인과 영향을 갱신했다(일시적 누락, 캐시가 스스로 고쳐짐, base_price는 채점에 쓰이지 않음, 11종, AVAX 69일+1). PROGRESS 표와 집계(치명 1, 높음 11, 중간 14, 낮음 7 / 미해결 29, 보류 3, 결정됨 1)도 상태 표와 일치한다. 반영됐다.
- 문서 수정 요청 16건: 1~16 모두 반영을 확인했다.
  - 요청 15(D-011)는 기한 대신 "이 경로를 백테스트·신호·모의투자 입력에 쓰지 않는다"는 경계를 두었다. 영향이 그 경로에 한정되므로 받아들인다.
  - 요청 12는 D-015로 등록됐다. 오염된 홀드아웃은 관문에서 뺐다. MDD만은 엄격하게 만드는 방향의 예외로 남겼다. 최종 관문은 26주 전진 모의투자다. CLAUDE.md 규칙을 완화하는 부분은 없다.
- 공개 저장소: 문서 5개에서 유니버스 총수, 패널 행 수, 캐시 종목 수, 보유 종목 수가 모두 빠졌다. 남은 "14종"은 G-Research 대회의 코인 수다.
- 잔여 항목(판정에 영향 없음, 다음 문서 수정 때 처리)
  - R-1(해결): `TODO_FOR_ME.md`의 잘못된 참조 "D-013 1~6"을 "D-015 ①"로 고쳤다.
  - R-2(해결): ISSUE-022 검증 줄 경로의 수직 탭 문자를 고쳤다. ISSUE-004 검증 줄과 이 문서에서 OOS 행 수도 지웠다(eval 요청).
  - R-3: ISSUE-010 제목의 "캐시 결측으로 남고"는 조금 강하다. 10-19 구멍도 다음 stale 동기화의 10일 겹침 구간에서 채워진다. 계속 남는 결측은 AVAX 2020처럼 Yahoo 이력 자체에 있는 구멍이거나, 10일 넘게 다시 동기화하지 않은 경우다.
  - R-4: ISSUE-003 본문의 FALLEN_COINS 봉 수(1,988~3,266)와 XMR·ZEC 하락폭(−16%, −32%)은 07:00 UTC 측정값이다. ISSUE-010의 07:36 UTC 값(1,989~3,267)과 측정 시각이 다르므로, 시각을 함께 적는 편이 좋다.
  - R-5(해결): 리드가 D-013~D-015를 확정했다. 최종 번호는 D-013 담당 지정, D-014 기준 통화, D-015 전략 채택 규칙이다.

## 2단계 wave A (2026-10-21)

- 판정: **조건부 통과**. 아래 차단 2건을 고친 뒤 verifier가 그 2건을 다시 확인하면 통과로 바꾼다. 나머지 항목은 반박하지 못했다.
- 대상: 미커밋 작업 트리(data, quant, eval, risk의 wave A 결과), 각 역할 보고서(scratchpad `phase2\{data,quant,eval,risk}_waveA.md`), `docs/dev/` 문서. 재학습, 실제 홀드아웃 로그 열람, 실제 DB 쓰기, paper CLI 실행은 하지 않았다.
- 상세: scratchpad `phase2\verifier_waveA.md`. 재현 스크립트는 scratchpad `verifier\w2a_*.py`다.

### 차단 문제
- **B-1(누수, 담당 eval. 고치는 방식에 따라 quant)**: `report.PointInTimeEdge`는 `행 날짜 + HORIZON_DAYS ≤ as_of`이면 그 행의 목표가 확정됐다고 본다.
  - `HORIZON_DAYS`는 주식 기준으로 최대 폭이 아니다. 5세션은 최대 11일까지 걸리고(9일 초과 113번), 21세션은 최대 35일까지 걸린다(32일 초과 235번).
  - 그래서 S1-1m에서는 walk_forward 결정일 3개(2017-01-31, 2018-12-31, 2023-01-31)에 목표가 다음 날 확정되는 행이 쓰인다. 그 행의 결과를 바꾸면 `edge_at` 출력이 바뀐다(`w2a_pit_holiday_leak.py`).
  - S1-1w(주말 결정)에서는 0건이다. ISSUE-029의 경계는 고정일 2025-10-19 기준으로 계산해 보니 지금은 안전하다.
  - 고치는 방법은 둘 중 하나다. 리드가 **재학습 전에** 정해야 한다.
    - (a) report.py가 실제 목표 종료일을 비교한다. 해시가 바뀌지 않는다.
    - (b) `HORIZON_DAYS`를 1w 11, 1m 35로 올린다. 해시가 바뀌므로 재학습 전에만 할 수 있다.
- **B-2(같은 조건, 담당 eval)**: 그날 그 자산군의 행이 하나도 없는 결정일에 두 구현이 다르게 동작한다.
  - S1은 `too_few_assets`로 전부 청산한다. `baselines.rank_rule_decisions`는 보유를 유지한다.
  - walk_forward 행이 `HOLDOUT_START − horizon_days`에서 끝나므로, 백테스트 창의 마지막 1~3주에 이 차이가 실제로 생긴다. S1은 현금, 기준선 ②는 보유다.
  - 교차 검사 테스트는 이 경우를 잡지 못한다(변형이 살아남음, `w2a_crosscheck_mutation.py`). 다른 규칙 변형 6개는 잡는다.
  - 기준선 ② 비교 전에 동작을 맞추고, 이 경우를 테스트에 넣는다. 백테스트 끝날짜 규칙도 실행 전에 기록한다.

### 확인한 항목
| 항목 | 결과 |
|---|---|
| pytest / ruff check / format --check | 331개 통과 / 통과 / 108 files already formatted |
| alembic | heads 하나(9f363af5cd85). 새 임시 DB에 upgrade head를 한 뒤 check: No new upgrade operations. 실제 DB(ro) 버전은 9f363af5cd85 |
| 기존 test_forecast 10개 | 본문 변경 없음. 합성 CV 두 곳에 `fixed_holdout=None`만 추가. 단독 실행 19개 통과 |
| 신호 입력 | `INPUT_COLUMNS`만 읽고 y·fr는 버림. as_of 날짜 행만 사용 |
| 체결·환율 | 다음 봉 시가 체결, 시가에는 전날 환율. 독립 재계산이 일치 |
| G-Research 피처 / 패널 날짜 shift | 누수 없음(코드와 테스트) / 독립 확인 11개 모두 참 |
| 실매매 잠금 | 켜는 패턴 0건, 유효 설정 False. `execute`는 값이 정확히 True일 때만 live 팩토리를 지연 호출하고, NotImplementedError면 paper로 대체하지 않고 `failed`. 킬스위치가 켜져 있으면 `halted`(메모리 스텁으로 확인) |
| 킬스위치·모의투자 | `run()`은 상태를 못 읽거나, 평가 불가, 음수, MDD·일일 손실 초과면 발동하고 `halted`로 기록. `transactions`에 쓰지 않음 |
| 홀드아웃·카운터 | CONFIGS_TRIED 3, STRATEGY 2, m=18(p=1로 채움). 로그 2줄 그대로. 로그 사본에서 같은 해시 재열람과 카운터를 올리지 않은 새 해시를 거부하는 것을 확인. 기준선 예비 구간 끝은 코드상 10-18 |
| STRATEGIES 사전 등록 | 「규칙 해석」은 결과를 보기 전에 원 문구의 충돌을 보수적으로 푼 것이라 카운터 2 유지가 타당. 비용 표는 `round_trip_costs()` 값(0.0080278 / 0.006)과 같음 |
| 데이터 수정 | `repro_partial.py`는 5개 경우 모두 확정 종가를 반환. 빈 갱신은 `synced_at`을 바꾸지 않음. 엄격 로더는 7개 실패 경우 모두 예외. Fake 대체 없음 |
| D-016 stamp | 실제 DB(ro) symbol_syncs 77행이 모두 10-21 01:38~02:12 UTC이고, 미래 값 0건(조회 시각 05:04 UTC). 근거와 맞음 |
| 기준선 ① 재계산 | 독립 스크립트: CAGR 28.83%, MDD 32.06%, Sharpe 1.14, 누적 +828.5%. 보고값과 같다. 차이 분해(연 CAGR): 원천징수 0.27%p, 거래 비용 0.32%p, 양도세 1.71%p(그중 최종 청산분 1.38%p) |
| 역할 분리 | 바뀐 파일은 모두 담당 범위 안. quant는 평가 코드를, eval은 signals·s1을 고치지 않음 |
| 문서 공개 정보 | 공개 유니버스 밖 티커 0건. 보유 수·수량·금액 없음 |

### 비차단 문제 (담당)
- N-1(risk): `PaperTrader.fill()`은 킬스위치를 보지 않는다. 그래서 발동 전에 승인된 대기 주문이 발동 뒤에도 체결된다. 지금은 모든 신호가 '우위 없음'이라 영향이 없다. 전진 모의투자 전에 고친다.
- N-2(eval): 관문 1의 `edge_share >= 0.5`는 STRATEGIES 반증 1("50% 이상이 우위 없음이면 기각")보다 경계에서 느슨하다. 분모(자산군 합산 여부, 처음 2년의 구조적 `insufficient_history` 포함 여부)도 wave B 실행 전에 고정한다.
- N-3(eval): `PointInTimeEdge`는 한 자산군 행이 없는 OOS에서 TypeError가 난다(report.py:353).
- N-4(eval): `test_committed_holdout_log_accepts_the_next_forecast_config`가 실제 로그 파일에 `open_holdout`을 호출한다. 사본을 쓰는 편이 안전하다.
- N-5(risk): ISSUE-012의 "test_paper.py 32건"은 실제 31건이다.
- N-6(리드): `strategy/evaluation.py`의 담당이 기록에 없다. 사실상 eval이다. `config.py`의 `strategy_budget_*`는 리스크 항목이 아닌데 risk가 추가했다(값은 S1 등록과 같음). D-013 보완을 권한다.
- N-7(eval·risk): wave B의 백테스트·관문에는 `RiskLimits.from_settings(settings)`를 넘긴다. 인자가 없으면 기본 `RiskLimits()`가 쓰여 설정값이 반영되지 않는다.
- N-9(리드): `train()`은 학습 전에 열람을 기록한다. 실패하면 같은 data_end로 다시 돌릴 수 없다. 실제 DB의 BTC는 10-20 봉이 아직 없다. Yahoo가 10-20을 다시 준 뒤 한 번에 실행한다.
- 그 밖: `HoldoutAccess`는 직접 만들 수 있다(실수 방지용 장치). OOS 행이 있는지가 미래 목표가 있는지에 달려 있다(전략 유니버스는 결측이 없어 영향 없음). CRLF 파일 4개. 1회 주문 상한 5% 때문에 S1과 기준선 ②는 비중을 천천히 채운다(노출을 보고할 것).

### 재현 명령
backend에서 실행한다. `SP`는 scratchpad 경로다.
```
py -3.11 -m uv run pytest ; py -3.11 -m uv run ruff check . ; py -3.11 -m uv run ruff format --check . ; py -3.11 -m uv run alembic heads
PYTHONPATH=. py -3.11 -m uv run python $SP/verifier/w2a_pit_holiday_leak.py     # B-1
PYTHONPATH=. py -3.11 -m uv run python $SP/verifier/w2a_crosscheck_mutation.py  # B-2
PYTHONPATH=. py -3.11 -m uv run python $SP/verifier/w2a_baseline1.py            # 기준선 ① 독립 재계산
PYTHONPATH=. py -3.11 -m uv run python $SP/verifier/w2a_{strict_loader,panel_shift,exec_gate}.py ; $SP/repro_partial.py ; $SP/verifier/empty_refresh.py
```

### 2단계 wave A 재확인 (진행 중)
- B-1의 quant 부분 확인(2026-10-21): `panel.HORIZON_DAYS`가 {1d: 5, 1w: 12, 1m: 35}로 바뀌었다.
  - exchange_calendars XNYS 전체 창(2006-10-23~2027-10-21)에서 재 보니, 1·5·21세션의 최대 폭이 5·12·35일(2006-12-29→2007-01-03, 2006-12-22→2007-01-03, 2006-12-12→2007-01-16)이다. 이 값을 넘는 경우는 0건이고, 코인 기간(1/7/30)도 덮는다.
  - `w2a_pit_holiday_leak.py`를 다시 돌렸다. 확정 행으로 잘못 세는 행이 0건이고, 그 결과를 바꿔도 `edge_at`이 같다.
  - 회귀 테스트 `test_panel.py::test_horizon_days_cover_the_longest_span_on_the_calendar`가 있다.
  - 재학습 전 변경이라 설정 3의 해시에만 반영된다. 함께 바뀌는 것: DM·HAC 지연이 5/12/35로 늘어나 더 보수적이다. walk_forward 끝(`HOLDOUT_START − horizon_days`)이 1w 12일, 1m 35일 전으로 당겨진다.
- eval의 report.py 방식 (a)와 B-2는 작업 중이다. 이번 조회 때 `baselines.py:128`의 E501로 `ruff check`가 실패했다(작업 중인 파일). pytest는 338개 모두 통과했다. 두 작업이 끝나면 B-1·B-2를 함께 다시 확인한다.
- N-1·N-5·N-7(risk) 확인(2026-10-21): 셋 다 해결.
  - N-1: `PaperTrader.fill()`(paper.py:630-658)은 대기 주문을 처리하기 전에 킬스위치를 본다.
    - 발동 중이면 대기 주문을 모두 취소한다.
    - 해제됐더라도 마지막 trip(`KillSwitch.last_trip_at()`) 이전에 승인된 주문(`created_at ≤ trip`)은 취소한다. 기록을 못 읽으면 `datetime.max`로 보고 전부 취소한다(fail-closed).
    - 취소된 행은 `expired`, `fill_note=kill_switch`, `risk_status=halted`가 된다.
    - 새 테스트 5건이 통과한다.
  - N-5: ISSUE-012 해결 줄이 35/12/52로 바뀌었고, `pytest --co` 수와 같다.
  - N-7: risk 쪽 기본값 동일성 단언을 확인했다. 백테스트·관문에 `from_settings`를 넘기는 일은 eval 몫으로 남는다.
  - 현재 트리: `ruff check`와 `format --check` 통과(108 files).
- B-1·B-2·N-2·N-3·N-4·N-7(eval) 확인(2026-10-21): 모두 해결.
  - B-1:
    - 이전 검사는 `HORIZON_DAYS`로 컷오프를 계산했다. 이번에는 그 상수와 무관한 독립 검사(`w2a_recheck.py`)를 썼다. 합성 OOS(전략 유니버스 19종, 실제 XNYS 세션)에서 1w·1m × 결정일 5개 × 두 자산군, 20개 경우를 보았다.
    - 실제 목표 종료일이 as_of보다 뒤인 행을 모두 바꿔도 `edge_at`은 같다(20/20).
    - as_of에 막 확정된 최신 행을 바꾸면 결과가 바뀐다(20/20). 즉 확정된 행은 빠짐없이 쓰고, 미확정 행은 쓰지 않는다.
    - `report.target_end_dates`(주식 h세션 뒤, 코인 h일 뒤)를 `_known`·`_hits`가 함께 쓴다.
    - `cv.walk_forward_end`는 `holdout_start − gap`(기간 + 엠바고)으로 더 보수적이 됐다. 이는 코드 변경이고 설정 3 재학습 전이다.
  - B-2:
    - 행이 없는 결정일에 기준선 규칙이 전량 매도한다(그날 비중 합 0.0).
    - 원래 구현(보유 유지)은 이제 교차 검사 테스트에 걸린다. 동점 순서를 뒤집은 변형도 걸린다. 규칙 변형 9개가 모두 S1과 다르면 실패한다.
    - 결정 종료 규칙(`walk_forward_decision_end`, 마지막 OOS 행 날짜)과 시뮬레이션 기간(`walk_forward_window`, 10-18까지)은 D-020에 wave B 전에 고정했다.
  - N-2: 이제 `edge_share > 0.5`여야 통과한다(정확히 0.5는 기각). 분모는 D-020에 고정했다: (결정일, 자산군) 조회 전부, 두 자산군 합산, 구조적 `insufficient_history` 포함. 사전 등록 문구에 맞는 엄격한 해석이다.
  - N-3: 한 자산군만 있는 OOS에서 `no_data`를 낸다(예외 없음).
  - N-4: 로그 테스트가 tmp 사본만 쓴다. 실제 로그는 2줄 그대로다.
  - N-7: D-020에 wave B 실행 규칙으로 적었다.
- 전체: pytest 341개 통과, `ruff check` 통과, `format --check` 108 files.

### 2단계 wave A 최종 판정 (2026-10-21)
- **통과**. 차단 B-1·B-2와 비차단 N-1~N-5·N-7을 고친 것을 재현으로 확인했다.
- 남은 비차단 항목은 wave B 이후의 기록 대상이다:
  - N-6: `strategy/evaluation.py`의 담당 기록(리드).
  - N-8: `HoldoutAccess`는 실수를 막는 장치일 뿐 강제 장치가 아니다.
  - N-9: 재학습은 Yahoo가 10-20 코인 봉을 다시 준 뒤 한 번에 실행한다.
  - N-10: OOS 행 존재가 미래 목표 유무에 달려 있다.
  - N-11: CRLF 줄 끝 정리.
  - N-12: 주문 상한 때문에 S1과 기준선 ②의 노출이 천천히 늘어나므로 노출을 보고한다.
  - N-13: 앱 안의 재학습이 홀드아웃을 기록 없이 채점한다.

## wave B 기준선 ①·② 사전 검증 (2026-10-21)
- 판정: **통과**(조건, 누수·홀드아웃, 수치, 재현성). 회전율 원인 설명만 일부 반박했다.
- 재실행 환경: 시장 데이터만 복사한 임시 DB에서 eval 함수를 두 번 돌렸다. 두 결과는 비트 단위로 같고 json과도 같다(CAGR 16.89%, MDD 39.11%, 회전율 11.108).
- 독립 구현: 순위 규칙, 달력, 사이징, 한도, 비용, 세금을 따로 구현했다(`wb_indep.py`, 모델 점수와 시세만 공유).
  - 결과: CAGR 16.894%, MDD 39.13%, 회전율 11.110. 일별 평가액 최대 차이 0.041%.
  - 결정일별 보유 집합은 eval과 완전히 같다.
- 누수·홀드아웃:
  - 입력 시세와 환율이 모두 2025-10-18에서 끝나고, OOS는 walk_forward만 있다(마지막 2025-10-01). 홀드아웃 로그는 2줄 그대로다.
  - 목표 4행을 손으로 계산해 OOS와 일치함을 확인했다. fold 퍼지 17일은 목표 최대 폭 12일(코인 8일)보다 길다.
  - IC 표를 재현했다(주식 t 1.70, 코인 t −1.24).
- 회전율:
  - 규칙 파일은 실행 전에 마지막으로 수정됐다. 사후 변경은 없다.
  - 회전율 분해: 순위 밴드 이탈 41%, 신규 진입 24%, 분할 매수·재배분 26%, 순수 드리프트 복원 9%. "주간 균등 비중 복원이 원인"이라는 eval의 설명은 주된 원인이 아니다. 주된 원인은 사전 등록한 순위 밴드 규칙과 점수의 주간 불안정성이다(eval에 문장 수정 요청).
- 비차단: 기준선 ②의 예산은 상수(`baselines.BUDGETS`)이고 S1 paper는 설정값(`budgets_from_settings`)이다. 지금은 둘 다 0.8/0.2다. wave B의 S1 백테스트도 같은 출처를 쓰도록 맞추거나, 실행할 때 값을 기록한다.
- 상세: scratchpad `phase2\verifier_waveB_baselines.md`
- 후속 확인(2026-10-21): eval이 `waveB_baselines.md` 「관찰」의 회전율 원인을 verifier 분해(41/24/26/9%)로 고쳤다. 처음 설명이 틀렸다는 것도 함께 적었다. 예산 출처는 이번 실행이 상수 0.8/0.2였고, 실행 시점 설정값도 같았다고 기록했다. S1 백테스트에서는 `budgets_from_settings` 하나로 S1과 기준선 ①·②에 넘기고 json에 남기기로 했다(wave B S1 검증 때 확인할 항목).

## wave B 본결과 (재학습 설정 3, S1 판정, 첫 모의투자) (2026-10-21)
- 판정: **통과**. S1-1w와 S1-1m의 기각은 구현 오류가 아니라 데이터에서 나온 결과다. 상세: scratchpad `phase2\verifier_waveB.md`.

### 재학습
- holdout_log는 3줄이다. 새 줄은 forecast 617b587dcee7, configs_tried 3이고 strategy 줄은 0이다.
- config_hash를 다시 계산하면 meta와 같다. report의 18개 판정을 Holm(18) × 3으로 다시 계산했고 불일치는 0이다. edge는 1d stock:range 하나다.
- oos_universe는 기간마다 참조 목록 밖 종목이 0개다(strategy 19, large_cap 30, training_only 19).

### 시점 기준 edge
- 독립 구현(`wB_edge.py`)으로 1,121개 조회의 사유 분포를 재현했다. eval 표와 칸마다 같다(edge 0).
- 판단 가능한 날짜의 rank 최대 t는 1.29이고 보정 전 p는 0.098 이상이다. 그래서 보정 구현과 무관하게 edge가 없다.
- 실제 OOS에 신호를 심으면 독립 구현과 eval 파이프라인(assess 경로 그대로) 모두 edge를 켠다. 두 결과는 자릿수까지 같다(s=0.01: edge 비율 0.765 / 0.659).

### 채택 관문과 진단
- 관문: 두 설정 모두 rejected(1·2·3·4·6 탈락)다. 전략 홀드아웃은 열지 않았다.
- 진단은 `not_adoptable`로 표시돼 있고 카운터에 들어가지 않는다.
- 독립 재계산: S1-1w의 edge 무시판에서 매수 45/66건이 정확히 같다. CAGR 17.67%(eval 17.66%), MDD 30.16%(eval 30.16%). S1-1m도 일치한다.

### 비교 조건과 모의투자
- 비교 조건: S1, 기준선 ①, 기준선 ②에 같은 budgets_from_settings 값(0.8/0.2), RiskLimits.from_settings, D-020 설정을 넘긴다. json에 예산, 한도, 허들이 기록돼 있다.
- 모의투자(ro 조회): paper_signals 0행, kill_switch_events 0행, `AM_LIVE_TRADING`은 False다. strategy 코드는 transactions를 참조하지 않는다. verifier에게는 실행 전 스냅샷이 없어서, 이후 비교용 해시만 scratchpad에 남겼다.

### 사후 변경
- 다음 가설 H-a~H-d는 목록만 있고 실행하지 않았다.
- STRATEGY_CONFIGS_TRIED는 2 그대로다.
- 규칙 파일(signals, s1, risk)은 재학습 전에 마지막으로 수정됐다.

### 비차단 문제
- W-1(eval): waveB_s1.md의 "주식 1w 기대수익 중앙값 약 54bp"는 1단계 보유 표본 값이다. 이번 run 전략 유니버스 값은 27.6bp다.
- W-2(eval): "t 3.5 이상 필요"는 근사다. Holm 18 × 3 기준으로는 z가 약 3.1 이상이고, 순서에 따라 더 높다.
- W-3(eval): json에 비용·세금 설정 전체가 기록되지 않았다.
- W-4(리드): 추적되지 않는 빈 파일 `backend/file`이 있다(만든 이 불명).
- W-5(quant): STRATEGIES.md S1의 상태 줄과 변경 이력을 기각으로 갱신한다(규칙 문구는 그대로).
- 추가 검증(리드 요청):
  - assess.py:
    - 홀드아웃은 S1-1w가 관문 ①을 통과했을 때만 열린다. 이번에는 열리지 않았다. walk_forward 행만 쓰고 시세는 10-18까지다.
    - 숨은 선택 1건(W-7, eval): S1-1m과 비교하는 기준선 ② 월간이 1m 목표 모델이 아니라 1w 목표 G-Research 모델 점수로 거래한다. 문서에 없다. S1-1m은 보고용이고 기각이라 판정에는 영향이 없다.
  - 홀드아웃 로그 테스트 변경: 정당하다. 일시적 상태 단정("최댓값 < CONFIGS_TRIED")을 불변식("≤")으로 바꿨고, 카운터 최댓값의 새 해시를 거부하는 검사는 그대로이며, 최댓값 + 1을 허용하는 검사가 추가됐다. 약화가 아니다.
  - 1m 수치를 독립으로 재계산했다(모두 일치):
    - 기준선 ② 월간: CAGR 24.64%(eval 24.63%), MDD 32.84%
    - 무작위판: 23.61%(eval 23.62%)
    - 모델판: 21.82%(eval 21.84%)
  - 해석 반박(W-6, eval): "무작위 > 모델이라 정보가 없다"는 1m만 고른 인용이다. 1w는 모델 17.66% > 무작위 10.73%다. seed는 하나이고 노출도 달라서(1m 0.67 대 0.87) 근거가 될 수 없다. 결론은 IC 검정으로만 뒷받침된다.
- 후속 확인(2026-10-21):
  - W-5(quant): 해결. STRATEGIES.md S1 상태가 기각(관문 ①, 홀드아웃 미개봉)으로 바뀌었다. 「이전 시도와 실패」 행과 변경 이력 2줄도 추가됐다.
    - 등록 규칙 문구 9곳(진입·유지 구간, 허들, 신뢰도 기준, 예산, n<3, 비용 표 2행, 26주)은 그대로이고, STRATEGY_CONFIGS_TRIED는 2다.
    - 「규칙 해석」의 N-2 항목은 D-020(15:51, S1 결과 17:16 전)의 결정을 옮긴 것이다. 사후 변경이 아니다.
    - 모델판과 무작위판 비교는 "참고(기각 근거 아님), 단일 seed, 노출 차이"로 적혀 있다(W-6 취지와 맞음).
  - W-1·W-2·W-3(eval): 해결.
    - waveB_s1.md는 27.6bp(전략 유니버스 주식)와 "p < 0.05/54, z ≈ 3.1"로 고쳐졌다.
    - waveB_s1.json에 costs, taxes, 초기 자본, fill, liquidate_at_end가 기록됐다(사후 기록 메모 포함). assess.py도 이제 이 값을 직접 기록한다.
    - pytest 전체 통과, ruff 통과, format 109 files.
  - W-6·W-7(eval): 미반영. waveB_s1.md 103행의 "무작위 > 모델 → 정보 없음" 문장이 남아 있다. 기준선 ② 월간이 1w 목표 모델이라는 사실도 아직 문서에 없다. 둘 다 비차단이다.

## 3단계 최종 판정 (2026-10-21)
- 판정: **통과**. 차단 문제는 없다. W-6과 W-7은 반영됐다.

### PROGRESS 「3단계 보고」
- 수치: 결과 비교, 통계 검정, 진단, 상위−하위 차이 표의 수치를 waveB_s1.json, waveB_baselines.json과 하나씩 대조했다. 모두 일치한다. verifier의 독립 재계산과도 맞는다.
  - 기준선 ①: 28.83%, 32.1%
  - 기준선 ② 주간: 16.89%, 39.1%, 11.1
  - 기준선 ② 월간: 24.63%, 32.8%
  - edge 무시판: 17.66%·45/66, 21.84%
  - 무작위판: 10.73%, 23.62%
  - HAC t: −3.91, −2.48, −3.43, −1.96
  - 상위−하위 차이 t: 0.94, −0.74, 1.16, 0.11
- W-6: 무작위판은 "참고, 근거 아님"으로 표시돼 있고, 1w와 1m 두 방향과 노출 차이를 함께 적었다. 결론은 IC, 상위−하위 검정, 비용 허들에만 근거한다. waveB_s1.md 105행과 STRATEGIES.md도 같다.
- W-7: 기준선 ② 월간에 "*" 각주(1w 목표 모델, 참고용)가 달려 있다. DECISIONS.md 294행에도 기록됐다.
- 조건 기재: 예산 0.8/0.2(설정값, 세 구성 공통), 한도(from_settings), 비용·세금, seed 0, run과 해시, 두 카운터(3, 2), 홀드아웃 열람 기록(예측 3건, 전략 0건)이 모두 적혀 있다.
- 기준선 ①의 MDD 32.1% 초과와 실서비스 상태가 사실과 맞다. 실서비스 상태: rank edge는 `FORWARD_CONFIRMED`가 비어 False, 모의투자 기록은 0행이고 사용자의 실행 예약을 기다림, 실매매는 false.

### STRATEGIES.md·TODO_FOR_ME.md
- STRATEGIES.md:
  - S1 상태는 기각(관문 ①, 홀드아웃 미개봉)이다. 결과와 원인이 있고, W-6 문장도 고쳐졌다.
  - H-a~H-d는 "후보, 미실행, 사전 등록 전"으로 표시돼 있다. 등록 규칙 문구는 그대로다.
- TODO_FOR_ME.md: 사용자 결정·실행 항목만 있다(대회명, MDD 확정, 세금 확인, 가설 선택, app-engineer 투입, 일일 실행 예약 등). 키, .env 내용, 보유 정보는 없다.

### docs/dev 전체와 최종 상태
- docs/dev 전체:
  - 공개 유니버스 밖 티커는 0건이다(약어만 남음). 보유 종목, 수량, 금액, 계좌 정보는 없다.
  - ISSUES.md 33건 모두 현상/원인/근거/해결/검증 5개 항목이 있다. 확인되지 않은 원인은 가설로 표시돼 있다.
- 최종 상태:
  - pytest 342개 수집, exit 0
  - `ruff check` 통과, `format --check` 109 files
  - `alembic heads` 하나(9f363af5cd85), 새 DB에 upgrade head 뒤 `alembic check`는 변경 없음
  - holdout_log 3줄, `backend/file` 삭제됨
  - `AM_LIVE_TRADING`을 켜는 설정은 0건이고, 유효값은 False다.
- git status에는 예상한 변경만 있다: 수정 17개, 새 코드·테스트·마이그레이션, docs/dev 7개(holdout_log 포함). `*.db`(-wal·-shm 포함), `backend/.env`, `backend/artifacts/`, `.claude/`는 .gitignore로 제외된다.

### 비차단
- W-8(리드·eval): PROGRESS 원인 1의 "시점 기준 IC의 t는 최대 1.26"은 마지막 결정일의 값(1w 코인)이다. 판단 가능한 전 결정일의 최댓값은 verifier 재계산으로 1.29다. 결론에는 영향이 없다. "마지막 결정일 1.26, 전 기간 최대 1.29"로 고치기를 권한다.
- 남은 기록 항목(이전 판정에서 넘어옴):
  - N-6: `strategy/evaluation.py`, `assess.py`의 담당 기록
  - N-8, N-10, N-11, N-12, N-13
  - ISSUE-026: `.claude/agents` 커밋 여부(사용자 결정)
- W-8 확인(2026-10-21): 해결. PROGRESS.md 264행, waveB_s1.md 99행, STRATEGIES.md 40행이 "마지막 결정일 1.26, 결정 가능한 전체 날짜 중 최대 1.29"로 고쳐졌다. 그 사이 코드 변화는 줄 끝(CRLF) 정리뿐이다(N-11 해결). models.py·store.py의 diff 통계는 이전 검증 때와 같고, 모델 파라미터는 run meta와 같다. pytest exit 0, ruff·format 통과, holdout_log 3줄. 남은 표현 차이 하나(비차단): STRATEGIES.md 40행의 "대략 t ≥ 3.5"는 W-2에 따라 "z ≈ 3.1 이상"으로 맞출 수 있다.
- STRATEGIES.md 40행 확인(2026-10-21): quant 수정 전 사본과 diff한 결과 40행 한 줄만 바뀌었다("대략 t ≥ 3.5" → "단측 z ≈ 3.1 이상"). 남은 비차단 항목 없음.
- STRATEGIES.md 40행 중간 확인(2026-10-21, 바로 아래 재확인으로 대체됨): 한때 40행이 PROGRESS·waveB_s1.md와 같은 긴 W-2 문구였다. 그 뒤 quant가 리드의 앞선 지시를 늦게 처리해 짧은 문구로 다시 바꿨다.
- STRATEGIES.md 40행 최종(2026-10-21, 리드 확정): "시점 기준 rank IC t는 마지막 결정일 1.26, 결정 가능한 전체 날짜 중 최대 1.29로, Holm m=18 × 3 기준(단측 z ≈ 3.1 이상)에 한참 못 미친다." 수정 전 사본과 diff한 결과 40행만 바뀌었다. 중복이 없고, 내용은 W-2 문구(첫 순서 p < 0.05/54 ≈ 0.00093, 단측 z ≈ 3.1)와 같다.
