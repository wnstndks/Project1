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

## S2-1d 사전 등록 (2026-10-22)
- 판정: **조건부 통과**. 차단 1건(B-1), 미완 1건(M-1). 상세는 scratchpad `phase3\verify_registration.md`.
- 대상: STRATEGIES.md 「S2 — 예측 변동성으로 SPY·BTC 노출 조절」, DECISIONS.md D-024·D-025, TODO_FOR_ME.md 1줄, scratchpad `phase3\` 설계·등록 문서와 합성 시뮬레이션 6개.
- 변경 감지 해시(sha256 앞 16자리): STRATEGIES S2 절 `fe3129194e59b93a`, D-024~D-025 `60dc7c2cded07964`. 이후 바뀌면 사후 변경으로 다시 본다.

### 확인한 항목
| 항목 | 결과 |
|---|---|
| 리드 최종 결정 6개와 세 문서의 일치 | 일치. 철회된 ewma σ̂ 대체·실제 비중 band 인자는 기각 대안으로만 남음 |
| 등록 전 결과 열람 흔적 | 없음. artifacts에 오늘 생긴 파일 없음, run 3 report.json(18개 비교, vol 없음) 그대로, holdout_log 3줄 |
| 합성 시뮬레이션 | `sizing_sim*.py`는 numpy·sys만 사용(시장 데이터·DB·네트워크 없음). 등록 표 4행, 정적 0.8/0.2 P ≥ 0.98, 래칫 4~7%p를 재실행으로 재현 |
| 규칙 모호성 | 초기 상태, 결측, 결정일, 체결, 래칫·밴드, 5% 주문 상한과 2% 허용오차(정체 없음, 경계 `>`가 문구와 같음) 확인. y·fr 미사용 |
| CLAUDE.md | OOS만 입력, '우위 없음', 레버리지 없음, 한도 설정값, `AM_LIVE_TRADING` 불변, 실보유·금액 없음, 누수 없음 |
| 기준선·다중검정 | 같은 기간·KRW·비용·세금. Holm m=24 × 3, 전략 m=2 × 3, DSR N=3 일관 |
| pytest / ruff | 385 통과 / 통과(2단계 코드 포함 작업 트리 스냅샷) |

### 발견한 문제
- B-1(quant): PIT vol edge의 Holm 순위가 같은 묶음의 다른 p값에 달려 있는데, `PointInTimeEdge`에 넣을 기간(1d만 대 1d·1w·1m)과 `rank_symbols`가 등록되지 않았다. 결과를 본 뒤 고를 수 있는 자유도다. "run 3 walk_forward 1d·1w·1m 전부, rank_symbols = strategy_symbols(), configs_tried 3(S1 assess와 같음)"을 규칙에 한 문장 추가하면 해결.
- M-1(eval): `evaluation.py`의 `STRATEGY_CONFIGS_TRIED`가 아직 2다. 3으로 올리고 주석을 남긴 뒤 백테스트한다.
- 비차단 N-1~N-10: 지수 ETF 상한 `max()` 구현과 D-025 "더 엄격하게만" 문구 차이(risk), 2단계 코드가 verifier 확인 전에 작업 트리에 들어옴(리드), 수치 표현 0.07~0.09 → 0.06~0.09, "두 종목 목표" 문구, 첫 결정일 명시, 반증 7의 NaN 처리, eval_design 반증 번호, 초안 파일 표시, 기준선 ② 재계산 확인, 2% 상수 중복.
  - N-2 사유(리드 확인 2026-10-22): 리드가 등록 완료 통보 뒤 "실데이터 계산 금지, 합성 테스트만" 조건으로 검증과 병행 구현을 지시했다. 절차 위반이 아니다. 실데이터 실행 흔적이 없다는 확인과 등록 절 해시에 의한 사후 변경 감시는 그대로 유지한다.

### 재현
- `py -3.11 -m uv run python -I <scratchpad>\phase3\sizing_sim6.py 3`(및 `sizing_sim2.py 1`, `sizing_sim4.py 3`), backend\에서.
- `grep -n "STRATEGY_CONFIGS_TRIED =" backend/app/strategy/evaluation.py`, `wc -l docs/dev/holdout_log.jsonl`.
- B-1 재확인(2026-10-22): **해결**.
  - 방법: 첫 검증 때의 S2 절 원문을 복원해(해시 `fe3129194e59b93a` 일치) 현재 절과 diff했다. 바뀐 줄은 6줄이다.
    - edge 항목 끝: PIT 판정 객체를 고정(run 3 walk_forward 1d·1w·1m 전부, `rank_symbols=strategy_symbols()`, `configs_tried=3`, min_years 2, lags `HORIZON_DAYS`, S1 assess와 같은 방식).
    - N-3: 0.06~0.09. N-4: 자산군별 결정일 문구. N-5: `FIRST_DAY` 2017-01-01. N-6: 반증 7에서 Sharpe가 NaN이면 기각. 「기준값의 근거」 첫 줄 정정.
  - 등록 수치(r, σ*, 밴드, 허용오차, 예산, 반증 1~9의 기준값)는 바뀌지 않았다. 모두 명확화이고 결과 열람 전이므로 카운터는 3 그대로가 맞다. 변경 이력에도 한 줄이 남아 있다.
  - 무결성: holdout_log 3줄, artifacts에 오늘 생긴 파일 0개.
  - N-8: `s2_rules_block.md` 첫 줄에 "대체됨" 표시가 있다. 해결.
  - 새 감시 해시: STRATEGIES S2 절 `e788b68a9686ce29`(116줄), D-024~D-025 `04ebacc8b17f7e1a`.
  - D-025 변경: "기존 수치 영향 없음"을 정정하는 항목이 추가됐다. 상한은 전역이라 기준선 ②를 다시 실행하면 수치가 바뀔 수 있고, eval이 다시 실행해 보고한다(N-9와 같은 내용). `symbol_cap`의 max 규칙도 적혔다.
- 남은 항목:
  - M-1(eval): `evaluation.py:36`이 아직 `STRATEGY_CONFIGS_TRIED = 2`다. 미완.
  - N-1(risk): 진행 중. D-025 367행과 `config.py`의 "0 < x ≤ 0.80, 더 엄격하게만"이 그대로라 0.20 미만 값에 효과가 없다는 점이 아직 드러나 있지 않다.
  - N-10: 요청 단계다.
- M-1·N-1 재확인(2026-10-22): **둘 다 해결**. S2-1d 사전 등록 판정을 **통과**로 바꾼다.
  - M-1: `evaluation.py:38`이 `STRATEGY_CONFIGS_TRIED = 3`이고 주석(S2-1d 등록, d1/d2는 세지 않음)이 있다. `assess.py`와 `assess_s2.py`는 이 상수를 Holm 배수와 DSR N으로 읽는다.
  - B-1 구현 대조: `assess_s2.py`도 1d·1w·1m walk_forward로 `PointInTimeEdge(oos, rank_symbols=strategy_symbols(), configs_tried=CONFIGS_TRIED)`를 만든다. 등록 문구와 같다.
  - N-1: `RiskLimits.symbol_cap`은 이제 `INDEX_FUNDS`에 `max_index_fund_weight`를 그대로 쓴다. 0.20보다 엄격한 값도 적용되고(`test_risk.py::test_a_tighter_index_cap_binds_even_below_the_symbol_cap`), D-025 「적용 방식」이 이렇게 고쳐졌다. `NO_LIMITS`는 `max_index_fund_weight=1.0`이다.
  - 등록 절 해시는 `e788b68a9686ce29`로 변화가 없다. D-024~D-025 해시는 N-1 문구 수정으로 `14fba22df12ecba4`가 됐다(diff는 「적용 방식」 3줄뿐).
  - 무결성: holdout_log 3줄, artifacts에 오늘 생긴 파일 0개. pytest 전부 통과, ruff 통과.
  - 남은 비차단: N-10(2% 상수 단일화, 요청 단계). N-9(기준선 ② 재실행)와 N-6(NaN 처리 구현)은 2단계 백테스트 검증 때 확인한다.
- risk 재확인(2026-10-22, N-1·N-10·state_reset): **통과**.
  - N-1: `symbol_cap`이 `INDEX_FUNDS`에 `max_index_fund_weight`를 그대로 쓴다. `check_order`의 사유도 맞고 `NO_LIMITS`는 1.0이다.
  - N-10: `paper.S2_MIN_ORDER_SHARE`가 없어졌다(grep 0건). `ExposureStrategy`는 `S2Config.min_trade_share`를 읽고, [0, 1) 밖이면 거부한다.
  - state_reset: 저장된 e·R을 읽을 수 없으면 0에서 시작하고, 경고 로그와 `state_reset` 플래그를 남긴다. 첫 결정은 리셋으로 치지 않는다. 기록은 `strategy_id`별로 조회한다(`_rows`). 0에서 시작하면 주간 결정일까지 증액하지 않으므로 보수적인 쪽이다.
  - `AM_LIVE_TRADING` 기본 False(config.py:38). true로 바꾸는 코드·설정은 0건이다. S2 모의투자의 edge는 `no_live_edge`다.
  - pytest 399 passed, ruff check 통과, format 112 files.
  - 해시: STRATEGIES S2 절은 `e788b68a9686ce29` 그대로다. D-024~D-025는 본문이 같고, 뒤에 D-026(eval 기록)이 붙으면서 구분 빈 줄 하나 때문에 해시가 `df81da38210b9620`으로 바뀌었다. D-026의 반증 7·8, m=24, 기준선 ② 한도, 허용오차 서술은 등록과 같다.
  - 비차단:
    - N-11(eval): D-026은 반증 7에서 "NaN이면 기각"이라고 하지만, `backtest.sharpe`는 분산 0이면 0.0을 돌려주므로 NaN 분기에는 도달하지 않는다. 둘 다 현금이면 0 = 0이라 "같으면 기각"으로 기각되므로 결과는 같다.
    - N-12(eval): 등록 진단의 "업비트 KRW 민감도(2021-10 이후)"가 `assess_s2.py`에 없다. 판정과 무관하지만 보고서에 생략 사유를 적어야 한다.
    - N-13(risk): 모의투자 실행기가 주간 결정일을 놓치면 그 주의 증액이 다음 주로 밀린다. 백테스트는 모든 날을 재생하므로 전진 모의투자 동안 실행 누락일을 기록·보고해야 한다.

## S2-1d 백테스트 결과 (wave C, 2026-10-22)
- 판정: **통과**. 관문 ① 기각(반증 1·2·3·4·7 해당, 5·6·8 통과)이 맞고, 보고 수치는 모두 재현된다. 상세는 scratchpad `phase3\verify_waveC_s2.md`.
- 사후 변경 없음:
  - 등록 절 해시 `e788b68a9686ce29`는 실행 전후로 같다. holdout_log는 3줄이고 artifacts에 새 파일이 없다.
  - assess_s2가 쓰는 코드는 모두 실행 시작(15:13 KST) 전에 고쳐졌다.

### 확인한 항목
| 항목 | 결과 |
|---|---|
| assess_s2 재실행 | eval JSON과 모든 필드 일치(차이 0개) |
| PIT vol edge 독립 재계산 | QLIKE 날짜별 차이 일치(최대 차이 0). XNYS 목표 종료일 불일치 0. 표본 36개 날짜의 사유·t·n 일치. 결정일 자기 행 미사용(누수 없음) |
| 규칙 재생(등록 문구로 따로 구현) | 결정 5,407개의 동작 전부 일치. 노출 차이 ≤ 3e-5(환산 상수 2.5632 대 2.563103) |
| SPY 별도 시뮬레이터 | 최종 평가액·세금·비용 일치(상대 차이 4e-16). 비용·세금이 실제로 차감됨 |
| 지표 | S2 CAGR 2.21%, Sharpe 0.44, MDD 10.7%, 비용 비율 24.4%. 대 ① t −3.89, 대 ② t −2.37. 연도 2/9. d2 Sharpe 0.512. SPY·BTC vol DM 4.21·0.029. 모두 일치 |
| 조건 동일성 | 같은 기간·비용·세금·자본. 한도와 허용오차의 차이는 등록대로. d1·d2 정의 일치 |
| 기준선 ②(N-9) | S1 보고값 16.89%가 결정 종료 2025-10-01에서 재현되고, 2025-10-08에서는 17.43%. SPY 최대 0.165라 D-025 상한의 영향 없음 |
| 코드 검토 | s2.py, risk.py, paper.py(state_reset), assess_s2.py, evaluation.py가 등록 규칙과 같다. y·fr 미사용. AM_LIVE_TRADING False |

### 발견한 문제
- ISSUE-034(eval, 비차단): S2 킬스위치 참고 발동 2024-12-31은 연말 양도세 납부(−2.80%p)를 일일 손실로 센 것이다. 그날 시장 움직임은 −0.26%였다. 판정에는 영향이 없다.
- N-14(eval): 보고서 원인 3의 근거 "고정 노출 ① Sharpe 1.13"은 BTC를 포함한 전 기간 값이다. 2021-08-02 이후로 다시 계산하면 S2 0.636, SPY 보유 0.667, 기준선 ① 0.871이다. 결론은 같으므로 근거 수치를 바꾸기를 권한다.
- N-15(quant·eval): σ̂ 환산 상수가 규칙(2.5632)과 검정(2.563103)에서 다르다. 둘 다 등록 문구와 같고 영향은 1e-5 수준이다.

### 재현
- backend\에서 `py -3.11 -m uv run python -m app.strategy.assess_s2 <out>`, `PYTHONPATH=. py -3.11 -m uv run python <scratchpad>\verifier\s2_pit_check.py <out>`, `s2_independent.py <out>`, `s2_killswitch_check.py`, `s2_post2021.py`
- 리드 추가 항목(2026-10-22):
  - edge 비율 집계: 분모는 주식 2,204(XNYS 세션 2017-01-03~2025-10-08)와 코인 3,203(UTC 날짜 2017-01-01~2025-10-08)을 더한 5,407이다. 분자는 주식 1,030 + 코인 0이다. 1,030 / 5,407 = 0.1905다. 분모 수는 규칙 재생과 달력에서 다시 셌다.
    - 주식의 첫 edge는 2021-07-30이다. 표본 대조에서도 2021-06-30은 보정 p 0.061, 2021-12-31은 0.0225였다.
    - 2021-07-30 이후 세션은 약 1,055개인데 그중 edge는 1,030개다. 중간에 꺼진 날이 약 25일 있다는 뜻이다.
    - 분자 1,030은 PointInTimeEdge 조회값이다. 표본 36개 날짜는 독립 재계산과 일치했다.
  - N-12 생략 사유: 타당하다. S2와 d2는 BTC 비중이 전 기간 0이었다(독립 재계산 최대 BTC 비중 0). 그래서 업비트 KRW 시세와 수수료로 바꿔도 S2 결과가 같다. 이 진단은 판정에 쓰지 않는다. d1(관문 무시)은 BTC를 들었으므로 업비트 민감도가 달라질 수 있지만, d1은 채택 불가 진단이라 결론에 영향이 없다.
- quant 공개 확인(2026-10-22): 결과가 나온 뒤 S2 절에 넣었다가 지운 두 줄(성공 기준 3 집계 문구, 변경 이력)은 남아 있지 않다. S2 절 해시는 B-1 재확인 때와 같은 `e788b68a9686ce29`이고, 변경 이력의 마지막 줄도 B-1 반영 줄 그대로다. 사후 변경은 없다.
  - 비차단 N-16(리드·quant): 관문 ③ 성공 기준 3("결정일의 50% 이상에서 신호가 정상 생성")은 자산군별인지 합산인지, `no_edge`를 정상 생성으로 볼지가 등록 문구에 없다. S2는 관문 ①에서 기각돼 지금은 쓸 일이 없다. 다음 전략은 등록할 때 정한다(이번 결과를 본 뒤 S2 문구를 바꾸면 사후 변경이다).
- risk N-13 재확인(2026-10-22): **통과**.
  - `run()`은 마지막 기록 뒤 놓친 결정일과 그중 주간 결정일을 경고 로그, `RunReport.missed`, 그날 기록의 rationale에 남긴다.
  - `missed_decisions()`는 읽기 전용이다. 첫 기록일부터 마지막 확정 봉까지 결정일·기록·누락을 세고, 데이터 결측으로 skip된 날도 누락으로 센다.
  - `paper gaps --strategy s2`는 날짜와 개수만 출력한다(금액 없음).
  - 래칫 규칙은 바뀌지 않았다. pytest 402 passed, ruff 통과, `AM_LIVE_TRADING` False.
- STRATEGIES.md S2 결과 반영 확인(2026-10-22, quant): **통과**.
  - 등록 본문(「### 가설」부터 절 끝까지)의 해시는 반영 전후 모두 `b3c9c57c34c23319`이다. 반영 전은 등록 검증본(e788…)에서 잘라 계산했다. 등록 문구와 기준값은 그대로다. 등록 본문 위에서 바뀐 것은 상태 줄(기각)과 새로 넣은 「결과」「원인 분석 (S2)」「교훈과 후속」「다음 가설 후보」뿐이다.
  - 수치(관문 표, edge 내역, 동작 횟수, 성과 4행, 진단 3행, 비용 0.5배, 코인 조회 비중 59%, N-14의 2021-08-02 이후 값)가 waveC_s2·verify_waveC_s2와 같다.
  - N-14·N-15·N-16·ISSUE-034·N-13이 후속 항목에 반영됐다. 「이전 시도와 실패」의 S2 행과 S1 후보 목록의 대체 표시가 들어갔다. 변경 이력에 기각 한 줄이 추가됐고 카운터는 3이다.
  - 사후 조정 금지(σ*, 밴드, 기간, 코인 제외, edge 정의 재시도 안 함)를 적었다. 다음 후보 C-1~C-4는 등록하지 않았다.
- eval·risk ISSUE-034·N-14 재확인(2026-10-22): **통과**. (eval의 처음 통보는 "표시 키만 추가"였는데, 검증하는 동안 "세금을 뺀 곡선으로 센다"로 바뀌었다. 아래는 바뀐 뒤의 코드 기준이다.)
  - ISSUE-034:
    - `run_backtest`가 날짜별 세금 납부액을 `BacktestResult.tax_paid`에 남긴다.
    - `summarize`는 `kill_switch_triggers(eq, limits, flows=-tax_paid)`를 쓴다. `_daily_loss` = 1 − (오늘 − flow)/어제라서 세금이 손실에서 빠진다. 입금은 손실을 가리지 않는다.
    - 낙폭 규칙과 채택 MDD는 세금을 낸 곡선 그대로라 판정은 바뀌지 않는다(D-003).
    - 이슈 수치로 다시 계산하면 2024-12-31 손실은 0.26%라 발동하지 않는다. S2 낙폭은 10.7%이므로 새 방식에서 S2 발동은 0회다.
    - `kill_switch_on_settlement_days`는 세금 납부일·최종일의 (낙폭) 발동만 표시한다.
    - 운영 킬스위치(`paper.py`의 `kill_switch_triggers`, `portfolio_breach`)는 flows 없이 불리므로 동작이 바뀌지 않는다(fail-closed 유지).
    - 테스트: `test_kill_switch_daily_loss_leaves_out_taxes_paid`(backtest), `test_daily_loss_leaves_out_taxes_and_other_cash_flows`·`test_drawdown_still_counts_taxes_paid`(risk). ISSUES.md 검증 줄을 갱신했다(처음에 verifier가 적은 "표시 키 하나만" 문장은 사실과 달라 지웠다).
  - 공개 확인: wave A·B·C 보고의 `kill_switch_count`는 이전 방식으로 센 값이다(참고값, ISSUE-034 영향 줄). 실행 뒤 `backtest.py`가 바뀌었으므로 지금 코드로 assess_s2를 다시 돌리면 킬스위치 참고 필드만 달라지고 성과·판정 수치는 같아야 한다.
  - N-14: waveC_s2.md 6절 원인 3이 2021-08-02 이후 값(S2 0.636, 노출 0.401, SPY 0.667, ① 0.871)으로 바뀌었고 단일 구간 참고치로 표시됐다. 4절 킬스위치 문단도 확인된 원인으로 고쳐졌다.
  - 비차단 N-17(eval): waveC_s2.md 125행의 경로가 `scratchpaderifier\s2_post2021.py`로 깨져 있다(`\v`가 제어문자로 바뀐 것으로 보임). `scratchpad\verifier\s2_post2021.py`로 고쳐야 한다. 4절·8절은 새 방식(세금 제외, S2 0회, 조치 전 JSON)과 맞는 것을 확인했다.

## 마무리 검증 (2026-10-22, 커밋 전)
- 판정: **통과. 커밋 가능.** 차단 문제는 없다.

| 항목 | 결과 |
|---|---|
| PROGRESS.md 「S2-1d 결과」 | 관문 표, edge 내역, 성과 5행, 진단 3행, 위험 지표, 비용 0.5배, 미달 일수, 2021-08-02 이후 값이 verify_waveC_s2와 같다. 금액은 데모 자본(1억원) 백테스트 값뿐이고 실보유 정보는 없다 |
| ISSUE-034 최종 | risk의 `flows` 인자(일일 손실만 세금·입출금 제외, 낙폭은 세후 곡선)와 eval의 `tax_paid`, `summarize(flows=-tax_paid)`가 연결돼 있다. 운영 킬스위치는 flows 없이 동작한다. ISSUES.md 5개 항목 형식이 지켜졌고 risk·eval 문구가 모두 남아 있다 |
| 최종 코드로 assess_s2 재실행 | eval JSON과 다른 것은 킬스위치 참고 필드뿐이다. S2 1→0, d2 1→0, d1 4→3, 기준선 ① 56→55, SPY 38→37, `kill_switch_on_settlement_days`가 새로 생김. 관문·성과·진단 수치는 모두 같다 |
| waveC_s2.md N-14 | 반영됨 |
| TODO_FOR_ME.md | C-1~C-4 선택 항목, 지수 ETF 상한 확인, S2 모의투자 실행·누락 안내. 사용자 결정·실행 항목만 있다 |
| pytest / ruff / format | 405 passed / 통과 / 112 files |
| alembic | 새 DB에 upgrade head를 하면 head 9f363af5cd85이고, `alembic check`는 "No new upgrade operations detected" |
| AM_LIVE_TRADING | 기본 False(config.py:38). true로 바꾸는 코드·설정은 0건 |
| 커밋 대상 | 수정 25개와 새 파일 4개(`s2.py`, `assess_s2.py`, `test_s2.py`, `frontend/.../HoldingsList.tsx`). `*.db`(-shm·-wal 포함), `backend/.env`, `backend/artifacts/`, `.claude/`는 .gitignore로 제외된다. frontend/ 변경은 기존 사용자 작업이라 이번 커밋 대상이 아니다 |
| 등록·홀드아웃 | 등록 본문 해시 `b3c9c57c34c23319`, holdout_log 3줄 |

- 비차단:
  - N-17(eval): 해결. waveC_s2.md의 경로 제어문자가 0건이다.
  - N-18(risk·리드): TODO_FOR_ME가 기각된 S2의 모의투자를 매일 실행하라고 안내한다. 지금은 '우위 없음'과 노출 0 기록만 쌓이므로 선택 사항으로 표시하기를 권한다.
  - 참고값: waveC·PROGRESS의 기준선 킬스위치 횟수(56 등)는 ISSUE-034 이전 방식으로 센 값이다. ISSUES에 공개돼 있다.
- 커밋 후 확인(2026-10-22, 3522ef0): 커밋에는 21개 파일(backend 15, docs/dev 6)만 들어갔다. frontend/, `*.db`, `.env`, artifacts, `.claude/`는 없다. 커밋된 이 파일의 N-17 줄에 verifier가 실수로 넣은 제어문자(VT) 2개가 있었다. 작업 트리에서 고쳤으며 후속 커밋이 필요하다. docs/dev의 다른 파일에는 제어문자가 없다.

## 화면 개편·유명 투자자 비교·규칙 점검 (2026-10-23) — 백엔드
- 판정: **통과. 차단 문제 없음.** 비차단 5건(N-19~N-23). 프론트엔드는 다른 verifier가 본다.
- 범위: 미커밋 작업(브랜치 agent-team)의 백엔드와 docs/dev. 실제 DB·`.env`는 읽기만 했고, 실제 서버(8001, 실제 공급자)는 GET만 보냈다. 보고에 실제 보유 종목·수량·금액은 적지 않았다(개수만).

### 확인한 항목
| 항목 | 결과 |
|---|---|
| pytest / ruff / format | `py -3.11 -m uv run pytest` **553 passed**(131초). `ruff check .` 통과. `ruff format --check .` 128 files already formatted |
| alembic | 새 임시 DB(`sqlite:///<scratchpad>/verifier/alembic_check.db`)에 `upgrade head` → `9f363af5cd85 → e8db9ec1f27b(guru_holdings·guru_syncs·cusip_tickers) → 6de1dd6fc3d6(rule_settings)`. `alembic heads`는 `6de1dd6fc3d6` 하나. `alembic check`는 "No new upgrade operations detected" |
| openapi | `npm run gen:api`를 두 번 실행해 `openapi.json`·`schema.d.ts`의 md5가 같다(생성이 결정적이고 작업 트리 결과가 현재 백엔드 스키마와 같음). `git diff --stat src/api/`는 HEAD 대비 이번 작업의 변경(4파일)이라 비어 있을 수 없고, 재생성으로 바뀐 줄은 없다. `npx tsc -p tsconfig.app.json --noEmit` exit 0 |
| A. 일간 변동(`services/portfolio.py`) | `_prev_close`는 quote 날짜(`quote.as_of.date()`) 이전 14일 캐시 봉 중 마지막 종가. yfinance quote의 `as_of`는 마지막 일봉 날짜라 한국 낮에는 전일 미국 세션 변동이 된다. KRW 코인은 업비트 원화 봉(`KRW-*`) 대비. 이전 봉이 없으면 `prev=price`(변동 0). 실제 서버 보유 종목 6개(주식, USD)에서 `day_change = quantity×(price−prev_close)`, `day_change_pct = (price/prev_close−1)×100`, `day_change_krw = day_change×환율`이 6/6 일치. `summary.day_change(_krw)` = 보유 합, `day_change_pct = Δ/(시가총액−Δ)` 일치. `prev_close==price`인 종목 0개. 테스트 `test_day_change_is_measured_from_the_previous_close`(USD·KRW 코인 둘 다) |
| A. sparklines·benchmark 라우트 | `GET /api/portfolio/sparklines?days=30`: 보유 6개, 종목이 holdings와 같고 길이 22(거래일). `days`는 7~365로 제한(422). 평가 통화(KRW 코인은 `KRW-*`) 종가는 `test_sparklines_read_closes_where_each_position_is_priced`. `GET /api/portfolio/benchmark`(curl로 스크래치 파일에 저장해 구조만 확인): 기본 5개(ARKK·BRK-B·SPY·QQQ·BTC-USD) 모두 `mine`과 같은 날짜 격자, `value_krw>0`. 스키마 `SparklineOut`·`BenchmarkOut`은 float, `HoldingOut`·`SummaryOut`의 새 Decimal 필드 4+3개는 `Num` |
| A. 예측 live 판정(ISSUE-037·D-028) | `report.live_edge_at`이 `comp.edge`를 먼저 읽는다(`report.py:495-499`). 현재 run `20261021T163606-f5e2aae3` report: 18개 비교 중 `stock:range 1d`만 `edge=True`, `configs_tried=3`. 실제 서버 `GET /api/forecasts/status`의 `live` 12칸: `stock 1d range`만 `forward_test_pending`, 나머지 11칸 `not_significant` — 기대값과 report에 일치. `GET /api/forecasts/held`(라우트가 `/{symbol}` 앞 65행에 등록) 6종목·3기간의 `direction_reason`/`range_reason`도 같은 값이고 `edge`는 모두 False(`FORWARD_CONFIRMED`가 비어 있어 범위 edge는 live에서 True가 될 수 없음). `low_ratio ≤ mid_ratio ≤ high_ratio`, `as_of < target_date` 전부 성립, as_of는 모두 마지막 확정 봉(10-22). 종목별 `GET /api/forecasts/{symbol}`도 6개 모두 200. 서비스는 `_horizon_rows` 하나로 `forecast`와 `held_forecasts`를 만들어 두 응답이 어긋날 수 없다. 테스트 `test_live_edge_reason_reads_the_walk_forward_verdict_first`, `test_status_live_verdicts_are_the_symbol_forecasts_verdicts` |
| A. 추론 캐시 키(ISSUE-040) | `_latest`의 키가 `(run_id, 보유 종목, _bar_epoch())`이고 `_bar_epoch`는 `calendar.last_final_date(SPY·BTC-USD, 오늘, now_utc)`. `market.now`/`utc_now`는 `MarketDataService.__init__`의 호출 가능 속성(99-100행)이라 테스트에서 시계를 바꿀 수 있다. 테스트 `test_inference_is_rebuilt_once_a_new_session_has_closed`. 서버는 새 코드로 재시작돼 있다(`/held` 라우트가 응답) |
| F. 외부 HTTP 격리 | `httpx2`(httpx) import는 `app/data/guru_provider.py`, 기존 `news_sources.py`·`upbit_provider.py`·`screenshot_extractor.py`뿐. `services/gurus.py`·`guru_compare.py`·`benchmarks.py`·`api/gurus.py`에는 HTTP 없음. 테스트는 `httpx.MockTransport`·`FakeGuruProvider`·`FakeCusipResolver`와 `tests/fixtures/gurus/`의 고정 파일 5개(ARKK·ARKW CSV, 13F 표·수정본 2개)만 쓴다 |
| F. 동기화 규칙 | `_sync_many`: TTL(ARK 24h, 13F 7d, 실패 뒤 1h) 판정 → 대상 투자자를 스레드풀로 먼저 모두 받고 → 투자자별 `_apply`에서 OpenFIGI 변환까지 끝낸 뒤 delete/insert/commit. 실패는 이전 보유를 두고 `guru_syncs.error`만 적는다(`test_failed_sync_keeps_previous_holdings_and_marks_stale`). `stale = as_of 없음 or error or 나이 > MAX_AGE(ARK 7d, 13F 140d)`. 동시 요청은 `_in_flight`로 중복 fetch 방지. 동기화는 요청 안에서 돌지 않고 BackgroundTasks(새 세션) |
| F. `AM_SEC_USER_AGENT` 비어 있을 때 | `sec_configured=False`면 13F 투자자는 fetch하지 않고 `SyncResult.error = "AM_SEC_USER_AGENT 미설정"`. 실제 서버 `GET /api/gurus`: 캐시 우드는 `source=ark, as_of=2026-10-22, stale=False, holdings_count=87, sync_note="갱신이 멈춘 펀드 파일 제외: ARKF(2026-01-02), ARKW(2026-10-06), ARKX(2026-01-02)"`; 13F 6명은 `synced_at=None, stale=True, error="AM_SEC_USER_AGENT 미설정", holdings_count=0`. `GET /api/gurus/compare`는 `syncing=False`, 캐시 우드 overlaps 3·top_missing 9, 13F는 0. `backend/.env`에 `AM_SEC_USER_AGENT`·`AM_LIVE_TRADING` 키 자체가 없다(값은 읽지 않음). `.env.example`은 빈 자리표시자. 코드·테스트·docs·frontend에 사용자 이메일 0건 |
| F. "같은 날 같은 돈" 곡선 | `cash_flows`: 매수 = 수량×단가+수수료, 매도 = 수량×단가−수수료를 그 거래의 환율(`trade_fx`: 기록된 `fx_rate`, 없으면 거래일 USD/KRW)로 원화 환산 — 장부 `Position.apply`의 원화 원금(`ledger.py:101`)과 같은 식. `replay`: 날마다 직전 종가(forward-fill)×그날 환율로 매수·매도, 첫 종가 전 흐름은 현금 대기, 과매도는 전량 매도. 벤치마크 쪽 수수료·세금은 없다(CLAUDE.md "수수료·세금 제외"). `test_benchmark_curve_equals_my_history_when_i_hold_the_benchmark`가 SPY 매수→SPY 벤치마크 = 내 곡선(원화 ±1원, 달러 ±0.01)을 46일 격자에서 확인. 시세는 장부에서 파생값을 만들기 전에 받는다 |
| G. 순수성·주문 없음 | `app/strategy/rules.py` import: math·pandas·numpy·`forecast.panel.AssetClass`·`strategy.risk`(risk.py도 numpy·pandas만). DB·네트워크·HTTP import 0건. `rules.py`·`services/rules.py`·`api/rules.py`에 `execute`·`broker`·`place_order`·`submit` 0건. `Order`는 `risk.check_order`의 사전 점검 입력으로만 쓰인다. `KillSwitch(self.db).state()`는 읽기 전용(`trip`은 호출하지 않음) |
| G. `AM_LIVE_TRADING` | `config.py:45` 기본 False, 검증기는 "true"/"false" 정확한 단어만 허용. `true`로 바꾸는 코드·설정 0건(`test_no_file_turns_live_trading_on`, `test_env_example_ships_live_trading_off`). `rules` 응답의 `live_trading`은 표시용이고 실제 서버 응답 False |
| G. 설정값 | `AM_RULES_*` 11개 + `AM_RULES_CRYPTO_*` 3개 + `AM_RULES_MAX_RISK_PCT`가 `config.py`에 범위 검증과 함께 있고, 빈 문자열은 전역값(`_rules_blank_is_global`). 서비스는 `RuleSettings.from_config(settings)`로 읽어 하드코딩 없음(`test_config_values_change_the_check`, `test_defaults_match_config_defaults`). 실제 서버 `GET /api/rules/settings`: 저장 행 없음(`updated_at=None`), global/crypto가 defaults와 같음(15/60/20/5/60/20/5/2/true/5/2.0, 코인 25/30/8) |
| G. 경계값 독립 검증 | 스크래치 `verifier\rules_boundaries.py` 51개 확인: 손절 −15% 등호에서 발동·1e-9 위에서 미발동, 추적 손절 고점×0.8 등호 발동·0.01 위 미발동, 60봉 밖 고점 무시, 현재가가 고점 갱신, 60일선 아래 5봉 발동·4봉 미발동, 63봉은 건너뜀·64봉은 판정, 추매 −5% 등호 발동·20일선 아래면 hold+info, 2회차 −10%, 3회차 없음, cut이면 add 미표시, 비중 15.0%는 통과·15.01%는 `max_position_weight`로 hold(조건은 나열), `weight_room` 4.99, 킬스위치는 추매만 막고 cut 유지, 코인 25/30/8, 종목>코인>전역, 목표 비중 등호 발동·20일선 무시, 기본값 안내 없음·10%×3 안내·7.5%×2 없음, `add_below_cut`, 리스크 1.5%/2.14%, `prob_below` 로그 선형 보간 수계산 일치·외삽 클립 0.01/0.99·역순 None, 라벨 "약 N%"/"10% 미만"/"5% 미만"/"90% 초과"/"95% 초과", `add_steps_done`(전량 매도 뒤 리셋, 부분 매도는 유지), 0 평균단가·100% 손절 거부. 50개 통과, 1개는 내 정확 등호 비교(0.9000000000000001 vs 0.9, 1e-16 차이)라 결함 아님 |
| G. 실제 데이터 재계산 | `GET /api/rules/check`(보유 6개, skipped 0, 킬스위치 미발동): 각 종목의 `GET /api/market/{symbol}/history`(400일)에서 60일·20일 단순평균, 60봉 고점(high)과 현재가의 max, 60일선 아래 연속 봉 수를 따로 계산해 `levels.ma_long`·`ma_short`·`trailing_high`·`below_ma` 트리거의 "N일 연속" 숫자·`bars`(276)·`as_of`(마지막 봉)와 6/6 일치. `cut_loss_price = avg_cost×(1−X%)`, `cut_price = max(손절, 추적)`, `add_price`, `cut_distance_pct`, 자산군별 X(주식 15)도 일치. 결과 분포는 cut 5(below_ma 5·trailing_stop 4, cut_loss 0)·hold 1, `blocked_by` `max_position_weight` 3건, `total_risk_pct_equity` = 각 `risk_pct_equity` 합. 라벨은 발동 조건과 price/avg_cost 관계에 맞는 값이었다 |
| G. prob_below | `cut_prob_1m`은 `prob_below`(분위수 로그 선형 보간, D-027), `cut_prob_1m_label`은 구간 텍스트(실제 응답에 "약 N%"·"90% 초과"·"95% 초과"만 등장), `labels.prob_caveat`에 `PROB_CAVEAT_KO`. 1m 기간을 쓰며 KRW 코인은 `krw_rate`(없으면 오늘 환율)로 달러 수준으로 바꾼다 |
| 가져오기 수정 | `PreviewRow`/`PreviewRowOut`에 `warning`. 상수 20배·±2%·USD ±50%·KRW ±5%·환율 밴드 500~3000 확인. 스크래치 `verifier\import_boundaries.py` 30개 모두 통과: 비율 20·1/20 등호에서 경고, 19.99·1/19.9는 없음, 수익률 ±2% 등호(1.95% 일치·2.1% 불일치→20배 규칙으로 넘어감), `_cost_agrees` 1.5/0.5 등호 일치·1.5001 불일치, KRW 1.05/1.0501, 역산 세 공식(`평가금액−손익` 우선, `/(1+수익률)`, `손익/수익률`), −100%·음수·수익률 0은 None, 부호 파서(`-`·U+2212·`▼`·괄호·`+`·0). `status=ok`일 때 `market`은 항상 있어 `Decimal(str(market))`이 안전(`_resolve`는 시세 실패를 `unknown`으로 돌림). 테스트 14개 중 토스형 역산·수익률 오독 교정·불일치 경고·28배 승자 무경고가 있다 |
| docs/dev | ISSUE-035~040 모두 현상·원인·근거·해결·검증 5항목을 갖추고, 미확인 원인은 "가설"로 표시(039·040). D-027~D-029 있음. TODO_FOR_ME는 사용자 결정·실행 항목만(`.env` 채우기, 단가·매수일 수정, 기본값 확인, 스케줄러). STRATEGIES.md는 C-2 선택 반영과 `STRATEGY_CONFIGS_TRIED` 3 유지. 실제 보유 수량·금액은 없다(N-21의 예시 금액은 아래 참고) |
| 커밋 대상 | `git check-ignore`: `*.db`(asset_manager.db·demo.db), `backend/.env`, `backend/artifacts/`, `.claude/`는 제외됨. **`frontend/.vitest/json/output.json`은 제외되지 않아 untracked로 보인다(N-20)** |

### 발견한 문제
- 차단: 없음.
- 비차단:
  - N-19(리드, docs): `ISSUES.md` 상단 표에 035·036·040 행이 없고(037~039만 추가됨) "합계 33건" 줄이 갱신되지 않았다(본문은 040까지 있음).
  - N-20(app-engineer/리드): `frontend/.vitest/json/output.json`(vitest JSON 리포터 출력)이 `.gitignore`에 걸리지 않는다(`git check-ignore` exit 1, 루트·`frontend/.gitignore` 모두 `.vitest` 없음). 커밋 전에 `frontend/.gitignore`에 `.vitest/`를 넣기를 권한다.
  - N-21(data-engineer, 가설): 예시 숫자 "〈실제 스크린샷의 평가손익·수익률 값〉(합성값으로 교체함)이 `screenshot_extractor.py` SYSTEM_PROMPT(96행)와 필드 설명(49행), `statement_import.py` 136행 docstring, `tests/test_imports.py`, ISSUES.md ISSUE-036에 쓰였다. ISSUE-036이 실제 스크린샷의 수익률을 7.89%로 적고 있어 이 손익 금액이 실제 계좌의 한 행일 가능성이 있다. 종목·수량은 없지만 공개 저장소 규칙("실제 금액을 쓰지 않는다")에 비추어 합성 숫자로 바꾸기를 권한다.
  - N-22(리드 CLAUDE.md, app-engineer): CLAUDE.md와 작업 설명은 sparklines를 "캐시만 읽음"이라 적지만 `PortfolioService.sparklines`는 `get_history`를 `max_age` 없이 호출해 마지막 동기화가 15분(`HISTORY_TTL`)을 넘으면 다시 받는다. 홈에서는 직전 `holdings()`(`_prev_close`)가 같은 심볼을 동기화해 실제로는 캐시에서 나오지만 코드가 보장하지 않는다. 문구를 고치거나 `max_age=HISTORY_TTL`을 넘기면 된다.
  - N-23(data-engineer, 낮음): `_signed_decimal`은 첫 숫자 앞의 기호만 본다. "7.89%▼"처럼 기호가 뒤에 오면 양수로 읽는다. 한국 앱은 대개 앞에 붙이므로 영향은 작고, 한계로 기록해 둔다.

### 재현
- backend\에서 `py -3.11 -m uv run pytest` / `py -3.11 -m uv run ruff check .` / `py -3.11 -m uv run ruff format --check .`
- `AM_DATABASE_URL=sqlite:///<scratchpad>/verifier/alembic_check.db py -3.11 -m uv run alembic upgrade head && alembic heads && alembic check`
- frontend\에서 `unset VIRTUAL_ENV; npm run gen:api; md5sum src/api/openapi.json src/api/schema.d.ts`(두 번 실행해 비교), `npx tsc -p tsconfig.app.json --noEmit`
- 경계값: `PYTHONPATH=. PYTHONIOENCODING=utf-8 py -3.11 -m uv run python <scratchpad>\verifier\rules_boundaries.py`, 같은 방식으로 `import_boundaries.py`
- 실제 서버 대조(GET만): `/api/forecasts/status`의 `live`와 `artifacts/global/runs/<run>/report.json`의 `comparisons[*].edge`, `/api/forecasts/held`, `/api/portfolio/holdings`+`/summary`(일간 변동 항등식), `/api/portfolio/sparklines?days=30`, `/api/portfolio/benchmark`(curl → 스크래치 파일), `/api/gurus`, `/api/gurus/compare`, `/api/rules/check`+`/api/market/{symbol}/history`(이동평균·연속 봉 수 재계산), `/api/rules/settings`

## 화면 개편·유명 투자자 비교·규칙 점검 (2026-10-23) — 프론트엔드
- 판정: **통과(차단 0, 비차단 10)**. 범위는 `frontend/`의 코드·테스트·빌드·dev 서버(5173) 서빙 모듈이다. 브라우저 화면 확인은 리드가, 백엔드와 `gen:api` 일치는 백엔드 verifier가 본다.
- 검증 기준 트리: `frontend/src` + `index.html` + `package.json` 파일 내용 sha1 합계 `4129b161595f8f81a7a25ce7d2590b1cf8b29891`(13:5x KST 최종 재실행). 검증 도중 다른 팀원이 `HoldingsList.tsx`·`HoldingsList.test.tsx`(13:35, 제목 칩 묶음 flex-wrap), `frontend/.gitignore`(13:46), `src/lib/holdings.test.ts`(13:48, 예시 숫자를 합성값 7.89/250·6000/250으로 교체, 로직 변경 없음)를 바꿨다. 13:46 재실행 해시는 `1b17f8bb…`였고 그 뒤 바뀐 파일은 `holdings.test.ts` 하나다. 아래 수치는 모두 최종 트리에서 다시 돌린 값이다.

### 확인한 항목
| 항목 | 결과 |
|---|---|
| 빌드 | `npm run build`(tsc -b + vite) 통과. 청크: recharts는 공유 청크 `ComposedChart-*.js`(361 kB) 한 곳, lightweight-charts는 `AssetDetail-*.js`(215 kB) 한 곳. 진입 청크 `index-*.js`(353 kB)와 Dashboard·Compare·Rules·Import·Transactions·Projection 청크에는 두 라이브러리 문자열 0건. `main.tsx:14-26` lazy route 7개(`/compare`·`/rules` 포함) |
| 린트 | `npx oxlint` 종료 코드 0, 경고 0 |
| 테스트 | `vitest run` 23 파일 127개 통과(13:31 첫 실행 126개 → 13:35 `HoldingsList.test` 변경 뒤 127개. 직전 보고 125개) |
| 순수 함수 라이브러리 | `lib/` 13개 모듈(forecast·format·indicators·holdings·quoteTime·priceChart·transactionChecks·history·rules·benchmarks·gurus·theme·split)에 짝 테스트가 있다. `sparkline.ts`·`ranges.ts`는 자체 테스트 없이 `Sparkline.test.tsx`·`history.test.ts`에서 간접 검증. 용어 함수(`modelStatusSentence`·`edgeLabels`·`reasonLabel`·`rangePhrase`·`midPhrase`·`weekRangeHint`·`isPastTarget`·`pendingPhrase`)는 모두 `lib/forecast.ts` 한 곳에 있고 `forecast.test.ts`가 문구를 글자 단위로 고정한다 |
| 독립 검산(vite-node, 스크래치 스크립트) | `isSuspiciousCost`: 2000/100 → true, 1999.99/100 → false, 5/100 → true, 5.01/100 → false, 음수·NaN → false(20배 경계 포함, 양방향). `sma([10,20,30,40,50,60],4)` = [null,null,null,25,35,45]로 직접 평균과 일치, n이 길이보다 크거나 0 이하면 전부 null. `dayChange(200→190)` = −10, −5%. `formatKrw(1234567.6)` = '1,234,568원', `formatKrwShort` 99,999 → '10만원', 9,999 → '9,999원', 1e8 → '1.00억원', `formatPct(0)` = '0.00%'. `formatDate('2026-10-23','long')` = '10월 23일 (금)'(달력과 일치). `weekRangeHint`는 `forward_test_pending`에서도 '오를 확률'을 붙이지 않고 `edge`에서만 붙인다. `modelStatusSentence` 출력에 '시장' 글자 없음 |
| 정직성 (a) 기준선 호칭 | `grep "시장 평균" src` 비테스트 0건. 기준선은 "단순 기준선(과거에 오른 날 비율)"·"EWMA 변동성"으로 적음(`forecast.ts:201`, `ForecastPanel.tsx:143`) |
| (b) 오를 확률 | `HoldingsList`는 `weekRangeHint`를 통해 `direction_reason === 'edge'`일 때만(`forecast.ts:99`). `ForecastPanel.tsx:202-212`는 edge면 본문, 아니면 작은 글씨로 "방향: 우위 없음 (모델 N% · 과거 평균 M%, 검증에서 차이 없음)". `PortfolioForecastCard`는 확률을 쓰지 않고 `modelStatusSentence` 한 줄. `PriceForecastChart.tsx:76`는 모든 기간의 `direction_edge`가 참이 아니면 "예측 띠는 변동 폭만 참고하세요. 오를지 내릴지는 우위 없음입니다"를 붙인다(테스트 3건) |
| (c) 중앙값 색 | `ForecastPanel.tsx:195-197`, `PortfolioForecastCard.tsx:75-85`와 "예상 중간값" InfoRow는 `text-ink`/`text-ink-2`, 부호만 있고 ▲▼ 없음. 차트 중앙값 선은 `--series-2` 점선. `PnL`(손익 색)은 운 나쁜 경우(ES95 손실 금액, `PortfolioForecastCard.tsx:202`)와 거래량 막대(상승일·하락일)에만 쓰인다 |
| (d) 투자 조언 아님 고지 | ForecastPanel:143-144, PortfolioForecastCard:216(접기 안), AssetDetail:209, Compare:38·115·301, Rules.tsx:77(`RULES_FOOTNOTE_KO`) + RuleCard 각주, Projection:81, 전 페이지 푸터 App.tsx:189 |
| (e) 신호 vs 규칙 점검 | '신호'는 `rules.ts:96`·`Rules.tsx:50`의 "예측 모델의 매매 신호는 현재 '우위 없음'" 두 줄뿐. 칩 `RuleStatusChip.tsx:17` title "내가 정한 규칙의 점검 결과예요. 예측이 아닙니다.", 배너 `RulesBanner.tsx:23`, 카드 각주 `RULES_FOOTNOTE_KO`("규칙 점검은 예측이 아니라 내가 정한 규칙의 결과입니다"), `rules.test.ts:122`가 필수 문구를 고정 |
| (f) 비교 화면 한계 | `Compare.tsx:36-38` ARK는 ETF이지 개인 계좌 아님 · 13F 분기 말 뒤 최대 45일 지연 · 롱 포지션만 · 현금/공매도/옵션 제외. `GuruHeader`(195-215)에 출처(`sourceLabel`)·기준일·종목 수·`stale` 배지·갱신 실패 문구. `AM_SEC_USER_AGENT`가 비어 있을 때 `needsSecUserAgent`(error에 'AM_SEC_USER_AGENT' 포함)로 `Compare.tsx:166-169`·`CompareCard.tsx:52-56`에 설정 안내를 보인다. 백엔드 `services/gurus.py:41 SEC_UA_MISSING = "AM_SEC_USER_AGENT 미설정"`과 맞음 |
| (g) 가져오기 | `Import.tsx:34` `include = ok && (new || delta) && !warning` → warning 행 기본 미선택. `price_estimated`면 단가 아래에 백엔드 `message`(없으면 "원화 매입금액÷오늘 환율로 추정") 표시(268-273), warning은 "확인 필요: …" 빨강(336) |
| (h) 단가 확인 배지 | HoldingsList.tsx:65, Dashboard.tsx:54(배너 개수), AssetDetail.tsx:90-95, Transactions.tsx:454·456(`needsPriceCheck`·`priceCheckRows` → `isSuspiciousCost`) 모두 같은 함수 |
| 데이터 규칙: 원화 | 금액 표시는 `useMoney().pick(usd, krw)`. 프론트에서 환율을 곱하는 곳은 모두 한 통화만 있는 값이다: 예측 분위수(`ForecastPanel.tsx:103-104`, `krw_rate ?? fx`, 환산 방식을 본문 138-142에 명시), 종목 시세 봉(`AssetDetail.tsx:58-67`, "달러 시세를 오늘 환율로 환산했습니다" 208), 규칙 수준·손실액(`RuleCard.tsx:52`, `Rules.tsx:655-656`), 원화 시뮬레이션의 달러 보기(`PortfolioForecastCard.tsx:47-49`, `Projection.tsx:149`). `Transactions.tsx:433-436`은 거래 레코드의 `usd_krw`(거래일 환율)로 반대 통화를 계산한다(N-FE-7) |
| 데이터 규칙: 입력·캐시 | `TransactionForm.tsx:105-107`·`Import.tsx:101-105` 수량·단가·수수료 문자열 전송(`TransactionIn`은 `number | string`). `useLedgerMutation`(`hooks.ts:79-84`)이 `transactions`·`['portfolio']`·`['corporate-actions']`·`['rules']` 4개를 무효화. `HoldingsList.tsx:27` `useHeldForecasts()` 1회, 행별 `useForecast` 0건. 규칙 점검도 `useRuleCheck()` 1회(홈 배너·목록·상세 카드가 같은 키) |
| 색상 | ts/tsx에 16진수 색 0건, `rgb()`/`hsl()` 0건. Tailwind 팔레트 색은 `HoldingsList.tsx:77 text-white` 1건(N-FE-1). `index.css` 토큰은 라이트 `:root`(16-38), 다크 `:root[data-theme='dark']`(41-63), `@media (prefers-color-scheme: dark) { :root[data-theme='system'] }`(66-90) 세 블록만. `prefers-color-scheme` 단독 `:root` 블록 없음(파일에 `prefers-color-scheme` 1회). 두 다크 블록 20개 토큰 동일, 라이트 토큰 이름·순서와 같음. `theme.test.tsx:380-395`가 이 세 조건을 실제로 검사한다(정규식으로 단독 블록 부정, 두 블록 텍스트 동일, 토큰 이름 배열 동일) |
| 테마 | `index.html:2` `<html data-theme="light">`, 프리페인트 스크립트는 저장값이 'dark'/'system'일 때만 바꾸고 try/catch. `theme.tsx` `DEFAULT_THEME='light'`, 키 `asset-manager.theme`, `isTheme` 가드로 쓰레기 값은 light, 저장 실패에도 동작(테스트 4건). `CandleChart.tsx:434-449` matchMedia change + `MutationObserver(data-theme)` → 상태 증가로 CSS 변수 재읽기, 정리에서 `disconnect()`·`removeEventListener` |
| 손익 색 | `--gain #d22030`(빨강)·`--loss #1b64da`(파랑). `PnL`(`ui.tsx:33-57`)은 색 + ▲▼ + 부호(`signed`, 진짜 마이너스 −). 매수 빨강·매도 파랑(`Transactions.tsx:578`, `chipTone`) |
| 접근성 | 중첩 `<a>` 없음: `HoldingsList.tsx:123-130` 단가 확인 링크는 `ListRow` 링크 밖이고 테스트가 `a a` 부재를 확인(291). 토글: `SegmentedControl` `role=radiogroup`+`aria-label`+`role=radio`/`aria-checked`+화살표 키(`ui.tsx:214-228`), 이동평균·벤치마크·투자자 칩은 `role=group`+`aria-pressed`. 이미지: 가져오기 썸네일 `alt`, 비중 막대·자산군 바 `role=img`+`aria-label`, 스파크라인 `aria-hidden`(수치는 텍스트에 있음), 범례 `aria-label="범례"`. 차트 svg 자체의 라벨은 N-FE-2 |
| 서빙 모듈 일치(5173) | 소스 대비 마커 수 일치: HoldingsList `weekRangeHint` 2=2, App "화면 테마" 1=1, lib/rules.ts 각주 1=1, Compare "13F" 2=2, Transactions `priceCheckRows` 2=2, Import `price_estimated` 2=2, PortfolioForecastCard `modelStatusSentence` 2=2. 서빙 index.html도 `data-theme="light"`. RuleCard.tsx 서빙본에 "내가 정한 규칙" 0건인 것은 문구가 `lib/rules.ts` 상수에 있기 때문(정상) |
| 커밋 대상 | `HoldingsTable.tsx` 삭제가 스테이지됨(`D `), `grep HoldingsTable src` 0건. `frontend/.vitest/`: 13:3x 확인 때는 `git check-ignore` 실패(`?? frontend/.vitest/`, 내용은 `json/output.json` 1개 = 10-22 vitest json 리포터 산출물, 57개 테스트 결과)였고, 13:46 `frontend/.gitignore:27`에 `.vitest/`가 추가되어 지금은 제외된다 |

### 발견한 문제
- 차단: 없음. (`.vitest/` 미제외는 검증 중 다른 팀원이 `.gitignore`에 추가해 해결됨.)
- 비차단:
  - N-FE-1(app): `HoldingsList.tsx:77` 아바타 글자색 `text-white`는 Tailwind 팔레트 색이다. 규칙은 `index.css` 변수만. 다크 모드에서도 `--series-1/2` 위 흰 글자라 가독성 문제는 없고, `text-surface`는 다크에서 어두워져 쓸 수 없다. 전용 토큰(예: `--on-series`)을 두거나 예외로 기록하기를 권한다.
  - N-FE-2(app): recharts 차트 svg는 `accessibilityLayer` 기본값으로 `role="application"`·`tabIndex=0`만 붙고 `title`/`desc`/`aria-label`이 없다(PriceForecastChart·BenchmarkChart·ValueHistoryChart·PortfolioForecastCard·ForecastPanel Backtest). `CandleChart`의 canvas 컨테이너 div에도 `role`/`aria-label`이 없다. 범례·툴팁·끝 라벨 텍스트는 있어 정보 자체는 읽을 수 있다.
  - N-FE-3(app): `RuleCard.tsx:52` 달러 수준(손절가·추매가·손실액)의 원화 환산이 오늘 환율인데 카드 안에는 그 말이 없다(`Rules.tsx:729` 미리보기 표 각주에만 "손절 시 손실은 오늘 환율로 환산한 원화입니다"). 허용된 예외(USD만 있는 값)지만 한 줄 표기를 권한다.
  - N-FE-4(app): 홈 `PortfolioForecastCard`의 "투자 조언이 아닙니다"(216)는 "기간별 예상 자세히" 접기 안에 있다. 항상 보이는 것은 `modelStatusSentence`의 "참고만 하세요"와 전 페이지 푸터(App.tsx:189)라 규칙 위반은 아니다.
  - N-FE-5(app): `holdings.test.ts`는 합성값 두 쌍(약 31.7배·24배)만 확인하고 정확히 20배 경계(포함)를 고정하지 않는다. 독립 검산으로 포함 동작은 확인했으니 경계 테스트 한 줄을 권한다.
  - N-FE-6(app): `fiftyTwoWeek`는 마지막 봉 날짜 −365일인 봉까지 포함해 366일 창이다(52주 = 364일). 영향은 미미하다.
  - N-FE-7(기록): `Transactions.tsx:433-436`은 거래 레코드의 `usd_krw`(거래일 환율)로 반대 통화 금액을 프론트에서 계산한다. 이번 wave 변경이 아니고(HEAD 대비 diff 없음) `TransactionOut`에 원화 금액 필드가 없어 유일한 방법이며, 오늘 환율이 아니라 장부와 같은 거래일 환율이다. `pick` 규칙의 예외로 CLAUDE.md에 적어 두기를 권한다.
  - N-FE-8(app): 단가 확인 판정의 기준 통화가 두 가지다. `HoldingsList.tsx:65`·`Dashboard.tsx:54`는 USD 필드(`avg_cost`/`price`), `AssetDetail.tsx:90-95`는 포지션 통화(KRW 코인은 `avg_cost_krw`/`price_krw`). 비율 비교라 결과는 사실상 같지만, 환율 변동이 큰 경계 근처에서 홈과 상세가 어긋날 수 있다(가설, 재현 안 함).
  - N-FE-9(기록): 검증 도중 소스가 바뀌었다(13:35 `HoldingsList.tsx`·테스트, 13:46 `.gitignore`, 13:48 `holdings.test.ts`). 모든 수치는 위 트리 해시의 최종 재실행 값이다. 커밋 직전에 `npm run build && npx oxlint && npx vitest run`을 한 번 더 돌리기를 권한다.
  - N-FE-10(가설, 리드): `frontend/.vitest/json/output.json`은 10-22에 `vitest --reporter=json --outputFile` 류 실행으로 생긴 산출물로 보인다. 이제 ignore되지만 작업 트리에 남아 있으니 지워도 된다.

### 재현
- `frontend/`에서(`VIRTUAL_ENV`가 잡혀 있으면 `unset VIRTUAL_ENV` 뒤) `npm run build`, `npx oxlint`, `npx vitest run`
- 청크 확인: `for f in dist/assets/*.js; do echo "$f $(grep -ci recharts $f) $(grep -ci lightweight $f)"; done`
- grep: `grep -rn "시장 평균" src`, `grep -rn "신호" src --include=*.tsx --include=*.ts`, `grep -rnE "#[0-9a-fA-F]{3,8}\b" src --include=*.tsx --include=*.ts`, `grep -rn HoldingsTable src`
- 독립 검산: 스크래치 `verify-fe/check.ts`(상대 경로로 `src/lib/*` import)를 `npx vite-node --root <frontend> <check.ts>`로 실행. vitest `--dir`로 루트 밖 테스트를 돌리는 것은 `/@fs/` 로딩 오류로 실패한다
- 서빙 비교: `curl -s http://localhost:5173/src/components/HoldingsList.tsx | grep -c weekRangeHint` 등 7개 파일
- 커밋 대상: `git check-ignore -v frontend/.vitest/json/output.json`, `git diff --cached --name-status`, `grep -rn HoldingsTable frontend/src`

### 최종 재실행 (리드 요청, 13:48 `holdings.test.ts` 변경 뒤)
- `npm run build` 통과(청크 구성 동일: recharts는 `ComposedChart-*.js`, lightweight-charts는 `AssetDetail-*.js`, `index-*.js`에는 둘 다 0건). `npx oxlint` 종료 코드 0·경고 0. `npx vitest run` 23 파일 127개 통과.
- 트리 해시(`frontend/src` + `index.html` + `package.json`) `4129b161595f8f81a7a25ce7d2590b1cf8b29891`. 리드가 이후 프론트 파일은 더 바뀌지 않는다고 알렸다.
- `holdings.test.ts` 변경은 예시 숫자만 바뀐 것으로 확인(함수 호출 두 줄, 기대값 true 그대로). 보고서의 N-FE-5 비율도 합성값 기준으로 고쳤다.

## F-2 유명 투자자 확장·하원 의원 거래 (2026-10-23) — 프론트엔드

검증자 verify-f2-frontend. 대상은 ded199d 이후 미커밋 변경 중 `frontend/`: 새 `src/lib/congress.ts`(+test), `src/components/CongressTrades.tsx`(+test), `src/pages/Compare.test.tsx`; 수정 `src/api/client.ts`(`congressApi`), `src/api/hooks.ts`(`useCongressTrades`·`useCongressStatus`·`useSyncCongress`), `src/pages/Compare.tsx`, `src/pages/AssetDetail.tsx`, `src/lib/gurus.ts`(+test, 15:54 SHORT_NAME 11명 추가), `src/api/openapi.json`·`schema.d.ts`(백엔드가 15:57 재생성). 기준 규칙은 CLAUDE.md 프론트엔드·문구·색상·유명 투자자 단락과 DECISIONS.md D-030. 화면 데이터 수치는 실제 DB라 인용하지 않았다.

### 판정: 실패(차단 1건, 수정 대기) — ISSUE-043
- **차단 1건** `npm run build` 실패(아래 1). 그 외 항목은 모두 통과.
- **비차단 4건** N-F2-FE-1~4(아래). 그중 하나는 ISSUE-044.
- 검증 트리 해시(`frontend/src` + `index.html` + `package.json`, sha1 of sha1sums) `0444ad0638457d0b8ee1923a043b11ef79067e44` (16:01). 검증 도중 소스가 바뀌었다(15:54 `gurus.ts`·테스트, 15:57 `openapi.json`·`schema.d.ts`). 수치는 모두 바뀐 뒤 트리에서 다시 돌린 값이다.

### 1. 빌드·린트·테스트
- `npm run build`: **실패**. `tsc -b`가 TS2322(`CongressTrades.test.tsx:32`)·TS2741(`Compare.test.tsx:53`) — 재생성된 `schema.d.ts`에서 `CongressStatusOut.syncing: boolean`이 필수가 됐는데 두 테스트 픽스처가 `syncing` 없이 `CongressStatus`를 만든다. `tsconfig.app.json`이 `include: ["src"]`라 테스트 파일도 타입 검사된다. 15:57 재생성 직전(15:56)에는 빌드가 통과했다(`CongressTrades-*.js` 5.38 kB 별도 청크, Compare 15.34 kB). ISSUE-043, app-f2에 전달.
- `openapi.json` 신선도: `app.export_openapi`를 스크래치로 뽑아 `diff -q` → 동일. `schema.d.ts`에도 `syncing`이 있어 두 생성 파일은 서로 맞다. 즉 생성 파일이 아니라 픽스처가 뒤처진 것이다.
- `npm run lint`(oxlint): 종료 코드 0, 경고 0.
- `npm test`(vitest run): 26 파일 150개 통과(직전 보고 26/149 + `gurus.test.ts`의 SHORT_NAME 1개). vitest는 타입 검사를 하지 않아 위 tsc 오류를 잡지 못한다.

### 2. 문구·정직성 — 통과
- `coverage_note`는 `CongressTrades.tsx:103`에서 `status.coverage_note`를 그대로 렌더한다. 프론트에 대체 문구 없음. 백엔드 `app/schemas/congress.py:6-10` 기본 문구에 하원·45일·금액 구간·본인/배우자/자녀/공동 계좌·상원 미포함·투자 조언 아님이 모두 들어 있고, 테스트는 다른(짧은) 가상 문구를 넣어 "그대로 표시"를 확인한다(`CongressTrades.test.tsx:9,122`).
- '신호'·'추천'·'예측': `grep -n "신호\|추천\|예측" CongressTrades.tsx congress.ts Compare.tsx` → 0건. 컴포넌트 테스트도 `document.body.textContent`에서 `/신호|추천/` 부재를 확인(`:158`).
- 매수/매도 배지: `CongressTrades.tsx:150` `bg-fill text-ink` 중립 배지. `text-gain`·`text-loss`·`▲▼`·`PnL`은 주석 두 줄에만 등장. 테스트 `:144-148`이 클래스·텍스트로 확인.
- 상단 안내(`Compare.tsx:36-40`): "트럼프 등 대통령·개인의 계좌는 공시되는 포트폴리오가 없어(연 1회 재산 공개는 금액 구간만) 비교 대상에 없습니다. 의원 거래는 하원 공시만 보여 줍니다." 포함. 카드 제목 "내 종목을 최근 거래한 미국 하원 의원".
- 미동기화 13F 투자자: `Compare.tsx:162-163` `needsSecUserAgent`(error에 `AM_SEC_USER_AGENT` 포함)로 나눠 `SecMissingCard` 한 장(`:199-209`)에 이름 목록 + 응답 `guru.error` 문구 + `.env` 안내(`SEC_HINT`). 백엔드 `app/data/gurus.py` 13F 17명(`source="13f"` 17줄)이 그 대상. 상위 20 종목 선택기(`HoldingsSection`)도 같은 필터로 제외. 테스트 `Compare.test.tsx:94-114`.

### 3. 데이터·훅 — 통과
- `useCongressTrades`(`hooks.ts:326-335`): `congressSymbolKey` = 대문자 → `Set` 중복 제거 → `sort()` → `,` join. `enabled: key.length > 0`(빈 배열이면 비활성), `queryKey: ['congress','trades',key,days]`, `queryFn`은 정규화된 심볼로 요청, `refetchInterval`은 `data.syncing`일 때 15초 아니면 false, `staleTime` 5분. `useSyncCongress`(`:347-353`) `onSuccess`에서 `['congress']` 무효화.
- Compare: `CongressSection`(`Compare.tsx:54-68`) `useHoldings().data.filter(asset_type === 'stock').map(symbol)` → 주식만. 테스트 `Compare.test.tsx:118-131` 가상 보유 3개(주식 2·코인 1) → 심볼 2개만 전달 확인. AssetDetail(`:148`) `position?.asset_type === 'stock' && <CongressMention/>` — 코인 상세·미보유 종목에서는 컴포넌트가 마운트되지 않아 훅 자체가 없다(코드 확인; 브라우저 네트워크 탭은 보지 않음). `AssetType` enum은 `stock|crypto`.
- `doc_url`(`CongressTrades.tsx:156-164`): `target="_blank"` + `rel="noopener noreferrer"` + `aria-label="{member} 공시 원문 (새 탭)"`. 테스트 `:151-154`.
- 독립 검산(스크래치 `check_congress.mjs`, Node 24가 `.ts`를 직접 import): `amountRange(1001,15000)`="$1,001~$15,000", `(250001,500000)`="$250,001~$500,000", `(50000000,null)`="$50,000,000 이상", `(1000001,null)`="$1,000,001 이상"; `ownerLabel` SP→배우자, dc→자녀(대문자 정규화), SELF→본인, 모르는 코드는 그대로; `sideLabel` sell_partial→"일부 매도", exchange→"교환", 모르는 값 그대로; `memberLine` 지역구→"Jane Doe (CA12) · 공동 계좌", 지역구 없으면 주(州), 둘 다 없으면 괄호 생략; `groupBySymbol` 최근 거래 종목 먼저·대소문자 무시; `distinctMembers` 2. 18/18 일치. 백엔드 파서(`congress_provider.py:283-286`)가 빈 owner를 항상 `SELF`로 채우므로 빈 owner 표시(" ·  계좌")는 실제 경로에 없다.
- `days`: 프론트 `CONGRESS_DAYS = 180`, 백엔드 `Query(180, ge=1, le=730)` 일치.

### 4. 서빙 모듈 일치 — 통과
- `curl -s http://localhost:5173/src/<file>`로 4개 파일 비교: `CongressTrades.tsx` `coverage_note` 2/2, `Compare.tsx` `대통령` 1/1, `hooks.ts` `refetchInterval` 3/3, `AssetDetail.tsx` `CongressMention` 2/2·`asset_type === 'stock'` 1/1. dev 서버가 현재 소스를 서빙한다(재시작 안 함). `congress` 단순 카운트는 Vite 변환(HMR import)으로 소스보다 많지만 토큰 비교는 일치.

### 5. 색상·접근성 — 통과
- 새 파일 hex 색 0건(`grep -nE "#[0-9a-fA-F]{3,8}"`). 쓰인 클래스 `bg-fill`·`text-ink(-2)`·`text-muted`·`text-danger`·`text-accent`·`divide-line`·`border-line`·`hover:bg-hover`는 모두 `index.css:94-107`의 `--color-*: var(--*)` 변수.
- 중첩 `<a>` 없음: 종목 `Link`는 `<header>` 안, 원문 `<a>`는 `<li>` 안, `CongressMention`은 `<p><Link/></p>`. 버튼은 텍스트 "지금 받기"(`type="button"`), 섹션 `aria-label="{심볼} 하원 의원 거래"`, 상태 문구 `role="status"`.

### 6. 커밋 후보 — 통과
- `git check-ignore -v`: `frontend/.vitest/` → `frontend/.gitignore:27`, `*.db` → `.gitignore:11`, `.env` → `.gitignore:19`, `frontend/dist` → `frontend/.gitignore:11`. `git status --porcelain`에 `.db`·`.env`·`dist` 없음.

### 비차단
- N-F2-FE-1(app, ISSUE-044): `CongressTrades.tsx:100` "(하루 60건씩)"은 백엔드 동작(한 트리거에 60건×최대 10배치, `AM_CONGRESS_MAX_BATCHES`로 설정)과 다르고 설정값을 화면에 하드코딩했다. 숫자를 빼거나 응답값으로.
- N-F2-FE-2(app, 가설): `CongressTrades.tsx:130,137` TradeRow key가 `doc_id:transaction_date:member:side:amount_low`. 한 PTR에 같은 종목·날짜·방향·구간 거래가 두 줄이면 React 중복 key 경고. DB는 `row_no`로 구분하지만 API에 없다. 백엔드 픽스처 `ptr_text_sample.txt`를 파서로 돌려 보면 5행 중 충돌 없음 → 재현된 사례는 없다. 배열 index나 `symbol`을 key에 더하면 사라진다.
- N-F2-FE-3(app): `Compare.tsx:65` 보유 조회가 실패하면 `symbols=[]`를 넘겨 카드가 "보유한 주식이 없어 보여 줄 거래가 없습니다."를 보여 준다. 실패와 보유 없음이 같은 문구다. 홀딩 오류는 같은 페이지 다른 섹션(`OverlapSection`)이 `ErrorBox`로 보여 주므로 사용자가 전혀 모르는 것은 아니다.
- N-F2-FE-4(기록): `CongressTrades.tsx:30`은 응답 루트 `trades.data.syncing`만 보고 `status.syncing`(이번 재생성으로 생김)은 쓰지 않는다. 심볼이 없어 status 쿼리만 도는 경우 동기화 중 표시가 없지만, 그때는 보여 줄 거래도 없어 영향이 없다.

### 재현
- `cd frontend && unset VIRTUAL_ENV && npm run build && npm run lint && npm test`
- 신선도: `cd backend && py -m uv run python -m app.export_openapi <scratch>/openapi.fresh.json && diff -q <scratch>/openapi.fresh.json ../frontend/src/api/openapi.json`
- grep: `grep -n "신호\|추천\|예측" src/components/CongressTrades.tsx src/lib/congress.ts src/pages/Compare.tsx`; `grep -nE "#[0-9a-fA-F]{3,8}" src/components/CongressTrades.tsx src/lib/congress.ts`; `grep -n "text-gain\|text-loss\|▲\|▼" src/components/CongressTrades.tsx`
- 독립 검산: 스크래치 `check_congress.mjs`가 `file:///.../frontend/src/lib/congress.ts`를 import(Node 24 타입 제거). `node check_congress.mjs`
- 서빙 비교: `curl -s http://localhost:5173/src/components/CongressTrades.tsx | grep -c coverage_note` 등 4개 파일
- 커밋 후보: `git check-ignore -v frontend/.vitest/ backend/app.db backend/.env frontend/dist`, `git status --porcelain`

### 최종 재실행 (app-f2 수정 뒤, 16:03 트리)
- app-f2가 16:03에 고쳤다: 두 픽스처에 `syncing: false`(`CongressTrades.test.tsx:37`, `Compare.test.tsx:58`), `CongressTrades.tsx:101` 문구를 "`{n}건 더 받는 중`"으로(배치 수 제거, 주석에 "backend settings"라고 적음), TradeRow key 끝에 배열 index 추가(`:130` `…:${i}`, `:137` `…:${SHOWN + i}`) — N-F2-FE-2 가설도 해소.
- 트리 해시 `3c5f93d2409b605b69272fc126f2c58b64da9a88`. `npm run build` 통과(`CongressTrades-*.js` 5.38 kB 별도 청크, `Compare-*.js` 15.34 kB). `npm run lint` 종료 코드 0·경고 0. `npm test` 26 파일 150개 통과.
- 재검사: '신호'·'추천'·'예측' 0건, hex 0건, 손익 색·▲▼ 0건(주석 제외). dev 서버 서빙 `CongressTrades.tsx` `더 받는 중` 2/2·`하루` 0/0·`coverage_note` 2/2 — 수정분이 서빙 중이다.
- 커밋 후보에 `.db`·`.env`·`dist` 없음. `backend/.env.example`(템플릿) 수정만 있다.
- **판정 변경: 통과.** ISSUE-043·044 해결 확인. 남은 비차단은 N-F2-FE-3(보유 조회 실패 시 문구)·N-F2-FE-4(기록)만이다.

## F-2 유명 투자자 확장·하원 의원 거래 (2026-10-23) — 백엔드
- 판정: **통과. 차단 문제 없음.** 비차단 12건(N-F2B-1~12; 그중 파서 누락 2행은 실제 공시 PDF로 재현함). 프론트엔드는 다른 verifier가 본다.
- 범위: 미커밋 작업(브랜치 agent-team, ded199d 이후)의 백엔드·CLAUDE.md·docs/dev. 실제 DB(`asset_manager.db`)·`.env`는 읽기만(`mode=ro`), 8001 서버에는 GET만 보냈다. 보고에 실제 보유 종목·수량·금액은 없다(의원 거래는 공개 자료라 적되 보유 종목과 연결하지 않음).
- 검증 도중(15:53~15:57) `services/congress.py`·`api/congress.py`·`schemas/congress.py`·`deps.py`·`config.py`·`.env.example`·`tests/test_congress_service.py`·`tests/test_congress_api.py`·`frontend/src/api/*`가 다른 팀원에 의해 바뀌었다(한 트리거의 배치 반복 `max_batches`, 상태 `syncing`). 아래 수치는 모두 그 뒤(16:03) 최종 상태 기준이고, 변경 파일 집합의 md5 묶음 해시는 `5039ae6c9e3b78f87b94fe360c1acde2`(`git ls-files -mo --exclude-standard -- backend CLAUDE.md docs/dev | sort | xargs md5sum | md5sum`, VERIFICATION.md 제외).

### 확인한 항목
| 항목 | 결과 |
|---|---|
| pytest / ruff / format | `py -3.11 -m uv run pytest` **602 passed**(122초, 15:57~15:59, 마지막 코드 변경 15:54 이후). 직전 보고 598 + 배치 반복·`syncing` 테스트 4개. `ruff check .` All checks passed, `ruff format --check .` 135 files already formatted(16:03 재실행) |
| alembic | 임시 DB `sqlite:///<scratchpad>/f2.db`에 `upgrade head` → `… → 6de1dd6fc3d6 → 3af66f72d79b(congress_trades)`. `alembic heads` = `3af66f72d79b` 하나. `alembic check` "No new upgrade operations detected". 생성된 `congress_trades`에 `UNIQUE(source, doc_id, row_no)`(`uq_congress_trades_source`)·`ix_congress_trades_symbol_date(symbol, transaction_date)`, `congress_docs` PK(source, doc_id), `congress_syncs` PK(source). 모델(`models.py`)과 마이그레이션의 컬럼·nullable 일치 |
| 의존성 | `pyproject.toml`에 `pypdf>=6.21.2`, `uv.lock`에 pypdf 6.21.2. `py -3.11 -m uv lock --check` "Resolved 100 packages"(갱신 필요 없음) |
| openapi | 15:57 재생성본 md5 `8e0cada1…`(openapi.json)·`5bb5c063…`(schema.d.ts). 내가 `npm run gen:api`를 다시 돌려도 md5 동일 → 작업 트리가 현재 백엔드 스키마와 같다. HEAD 대비 `git diff --numstat`는 396/245줄 추가(이번 작업의 congress 3경로·4스키마)라 비어 있을 수 없다. `client.ts`·`hooks.ts` 변경은 gen:api 산출물이 아니라 app 팀원 수정 |
| 1. 투자자 목록 | `GURUS` 18명 = ARK 1 + 13F 17(D-030의 11명 추가: 소로스·아이칸·막스·클라먼·리 루·게이츠 재단·파브라이·테리 스미스·댄 롭·NPS·Norges; 르네상스·그린라이트 제외 사유는 docstring). 17명 모두 `cik` 10자리 숫자·서로 다름, `expected_name` 비어 있지 않은 대문자(`test_guru_list_is_consistent`가 18·17·대문자·ARK는 None을 고정). CIK 숫자 자체는 EDGAR를 호출하지 않아(UA 미설정, 사용자 이메일 사용 금지) 독립 확인하지 않았다(N-F2B-12) |
| 1. 제출자 이름 검사 | `Sec13FProvider.fetch`(guru_provider.py 447-452): submissions JSON 파싱 직후 `check_filer_name` → 그 다음에야 `choose_filing_sets`·`_rows`(표 요청). `check_filer_name`은 `name`+`formerNames[*].name`을 upper로 비교하고 실패 시 `GuruDataError("CIK 불일치: EDGAR 이름 '…'에 '…'가 없음 (CIK …)")`. `test_sec_provider_refuses_cik_whose_edgar_name_does_not_match`가 MockTransport로 요청 수 1(표 미요청)을 고정, `test_filer_name_check_accepts_former_names_and_skips_without_keyword`가 formerNames 일치·키워드 없는 Guru 통과·빈 이름 실패를 확인 |
| 1. Norges fallback | `choose_filing_sets`가 보고 분기별 [원본, 이후 /A…] 묶음을 최신순으로 돌려주고, `fetch`는 `sets[:1+MAX_QUARTERS_BACK]`(=3분기)를 돌며 `EmptyTableError`면 다음 분기로, 성공 시 note "기밀 처리로 표가 비어 있는 분기 제외: …. … 기준 표를 표시", 셋 다 비면 `EmptyTableError`(빈 포트폴리오를 현재로 보여 주지 않음). `test_sec_provider_falls_back_to_previous_quarter_when_table_is_confidential`(Q2 빈 표→Q1, as_of 2026-03-31, note에 두 분기; 전부 빈 표→예외) |
| 1. 서비스 재시도·유지 | `services/gurus.py:_interval`: error가 `CIK 불일치`로 시작하면 FAIL_RETRY(1h) 대신 SYNC_TTL(13F 7일). `_apply` 예외 경로는 `guru_holdings`를 지우지 않고 `guru_syncs.error`만 갱신(as_of·note는 이전 값 유지). `test_cik_mismatch_is_not_retried_hourly` |
| 1. 실제 서버 | `GET /api/gurus` 18명. 캐시 우드 `ark, as_of 2026-10-22, stale False, 87종목`; 13F 17명 모두 `error="AM_SEC_USER_AGENT 미설정", stale True, holdings 0`. `GET /api/gurus/norges-bank/holdings?top=3` 빈 목록+같은 error, `GET /api/gurus/nobody/holdings` 404. `.env`의 `AM_SEC_USER_AGENT`는 비어 있음(값은 읽지 않음) |
| 1. 개인정보 | 사용자 이메일·`@gmail` 문자열: `backend/app`·`tests`·`.env.example`·`frontend/src`·`docs`·CLAUDE.md·이번 diff·untracked 파일에 0건. `congress_provider.USER_AGENT = "asset-manager (personal use)"`(`test_house_provider_fetches_index_and_ptr`·`test_default_client_declares_user_agent_without_contact`가 `@` 없음을 고정) |
| 2. 외부 HTTP·pypdf 격리 | `import httpx2`는 `congress_provider.py`·`guru_provider.py`·기존 3파일(news_sources·upbit_provider·screenshot_extractor)뿐, `pypdf` import는 `congress_provider.py`(29-30행)뿐. `services/congress.py`·`api/congress.py`·`schemas/congress.py`에 HTTP·pypdf 없음 |
| 2. 파서(코드 읽기) | `parse_ptr_text`는 첫 줄에서 NUL 제거(ISSUE-042), 머리글·"Filing ID #"·"P T R" 류 제거 뒤 "F S:" 라벨마다 flush. `_TXN`은 `(?<![A-Za-z])`로 단어 끝 P/S/E 오인 방지, `S (partial)`→`sell_partial`, `P (partial)`→`buy`, `E`→`exchange`. `parse_amount`: "Over $X"→(X, None). Owner 코드 SP/DC/JT, 없으면 SELF. `[XX]` 코드는 마지막 것을 asset_type으로, 티커는 자산명 끝 `(TICK)`만. Amended는 `filing_status`. 라벨이 없는 문서만 구형 경로 |
| 2. 파서 경계(내 입력 18건, 스크래치 `verify-be/probe_parser.py`) | 통과: 자산명 3줄 + `[ST]` 별도 줄 → 한 행·티커 유지, `Over $50,000,000`→high None, `[MF]` 티커 없음→symbol None, 알림일 없음→None, `P (partial)`→buy, `D :`+`F S : Amended`, 자산명 안의 날짜(국채 만기)·`$1,001-$15,000`(공백 없음)·자산 텍스트 안의 NUL·마지막 라벨 없는 행(filing_status None) 모두 정상, 달력에 없는 날짜 `13/45/2026`은 예외 아닌 warning. 한계: N-F2B-5(✓/Yes 다음 줄), N-F2B-6(한 글자 줄), N-F2B-7(SP로 시작하는 자산명), 타입 글자만 한 줄이면 warning(누락이지만 조용하지 않음) |
| 2. 실제 PDF 재파싱(공개 자료 6건, 스크래치 `verify-be-dl/`) | `congress_docs.error`가 있는 4건(20035390·20035491·20035445·20035553)+중복 의심 2건(20035464·20035434)을 서기국에서 받아 `extract_text`→`parse_ptr_text`. 6건 모두 "F S:" 라벨 수 = 행 수 + warning 수(57+1, 98+1, 1+1, 1+1, 5+0, 17+0), 행 수는 DB와 일치. 같은 문서 안의 동일 행 중복(BSX ×3, MSFT ×2 등 8문서)은 원문의 별도 행(각 행 아래 `S O: <계좌>` 소유 계좌 라벨이 다름)이라 파서 버그 아님. 자산명 'Ro'(OL, 소유 계좌 "TPT RO Affiliate I LLC")·`[MF}` 오타는 원문 그대로. 누락 2행은 N-F2B-1, 가짜 warning 2건은 N-F2B-2 |
| 2. 서비스 | `sync()`: TTL(24h, 실패 뒤 1h) → `_lock`으로 `_in_flight` 예약 → `_loop`. `_run` 한 배치: ①색인(올해·작년, 올해 404만 허용) ②`due`(PTR·filing_date ≥ now−365d, 최신순)에서 미저장 + 실패 재시도 60건 ③문서 전부 네트워크·파싱(메모리) ④`_store`(doc별 delete→add_all)+`_upsert_sync` → **commit 1회**. 색인 실패는 sync 행만 쓰고 commit(`test_nothing_is_written_when_the_first_index_fetch_fails`: trades·docs 0). `no_text`는 재시도 안 함, `failed`는 다음 배치 뒤쪽에. 새 `_loop`: 한 트리거가 색인은 1회만 읽고 최대 `max_batches`(기본 10, `AM_CONGRESS_MAX_BATCHES` 1~100) 배치를 1.5초 간격으로 반복, error·pending 0·진전 0이면 중단(`test_one_trigger_works_through_the_backlog_in_batches_with_a_pause`, `test_batching_stops_on_index_error_and_without_progress`). `status().syncing`은 `_lock` 아래 `_in_flight` 조회(`test_status_reports_syncing_while_a_run_is_in_flight`). 동시 호출은 `test_concurrent_sync_is_skipped_while_one_is_running` |
| 2. 스키마·API | `schemas/congress.py`: Decimal 필드 없음(int·date·str)이라 `Num` 불필요. `COVERAGE_NOTE_KO`에 "미국 하원"·"최대 45일"·"구간"·"본인·배우자·자녀·공동 계좌"·"상원은 포함되지 않습니다"·"투자 조언이 아닙니다" 모두 있음. 라우트 3개(`/api/congress/trades`·`/status`·`/sync`, 서버 openapi 확인). 핸들러는 provider를 직접 부르지 않고 `BackgroundTasks.add_task(run_sync)`만, `run_sync`는 `get_session_factory()`의 자기 세션. `/trades`는 `synced_at None and not syncing`일 때만 작업 추가. `days`는 1~730(`days=0`→422 확인) |
| 2. 테스트 네트워크·가상 데이터 | `test_congress.py`(17): `httpx.MockTransport`, PDF는 테스트 안에서 생성(`tiny_pdf`), 실 요청 없음(`HouseClerkProvider()` 기본 클라이언트는 헤더만 확인). `test_congress_service.py`(15)·`test_congress_api.py`(3): `FakeCongressProvider`. fixture 의원 Jane Doe·John Roe Jr.·Rich Aaronson, 지역 ST01, 티커 QQXA·ZYXW·WXYZ·FZZB·KNWN은 가상(단 ACMR은 실제 상장 티커, N-F2B-10) |
| 3. 실제 서버 상태 | `GET /api/congress/status`(16:02): synced_at 2026-10-23T06:33:54Z, index_modified 2026-10-22T13:00:38Z, stale false, syncing false, error null, docs_total 529, docs_parsed 51, docs_no_text 9, docs_failed 0, docs_pending 469, trades 588. 받은 60건 중 no_text 9건 = **15%**(D-030의 "약 12%, 가설"과 비슷). no_text 9건은 모두 7자리 DocID, parsed 51건은 모두 8자리(종이 제출 = 7자리 가설과 일치) |
| 3. 실제 거래 필드(읽기 전용 SQL + API) | 588행 전부: transaction ≤ notification ≤ filing 위반 0, amount_low < amount_high 위반 0, notification null 0, side ∈ {buy 243, sell 153, sell_partial 184, exchange 8}, owner ∈ {SELF 316, JT 122, DC 91, SP 59}, asset_type 상위 ST 512·GS 59, 금액 구간 6종, symbol 266종(null 72행 = 채권·펀드), 의원 33명·18개 주. 보유 종목이 아닌 `MSFT`로 `GET /api/congress/trades?symbols=MSFT&days=365`: 13행, doc_url 모두 `https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/<8자리>.pdf`, 날짜 순서·금액 정상(예: Lisa McClain MI09 SP buy 2026-09-30/10-01/10-12 $1,001-$15,000). `days=5`→0행, symbols 없음→0행. `cap_gains_over_200`은 588행 모두 None(N-F2B-5) |
| 4. docs | ISSUES.md 표 42행, 심각도 1+13+19+9=42, 상태 29+9+3+1=42로 합계 줄과 일치. ISSUE-041·042는 현상·원인·근거·해결·검증 5항목, 미확인 원인은 "가설" 표시(041 왜 Q1·Q3만인지, 042 7자리 DocID). CLAUDE.md 유명 투자자 단락: 18명·17명 이름·`expected_name`·Norges 2분기·`congress_*` 3테이블·3엔드포인트·`coverage_note`가 코드와 일치. "한 번에 최대 60문서"는 배치 반복 추가 뒤 불완전(N-F2B-9) |
| 4. 안전·커밋 대상 | `config.py:45` `live_trading: bool = False`, `.env.example` `AM_LIVE_TRADING=false`, True로 두는 코드 0건. `git status --untracked-files=all`에 `*.db`·`.env`·`artifacts/`·`.vitest/` 없음(`git check-ignore`: 루트 .gitignore 11·19·24행, frontend/.gitignore 27행) |

### 발견한 문제
- 차단: 없음.
- 비차단:
  - N-F2B-1(data-engineer, 재현됨): 금액 하한 "$X -"와 상한 "$Y"가 **페이지 경계**로 갈라지고 그 사이에 자산명 나머지 줄이 오면 행을 버린다. `_parse_chunk`의 `_AMOUNT_TAIL`이 `^\s*\$`로 바로 뒤만 보기 때문(congress_provider.py:206, 269-272). 실제 20035491 원문: `JT Devon Energy Corporation Common S (partial) 09/02/2026 09/15/2026 $100,001 -` / [페이지 머리글] / `Stock (DVN) [ST] $250,000` → warning "amount upper bound missing", DB에 DVN 09/02 행 없음. 20035390의 LAMR 08/19 행도 같은 패턴(DB에는 LAMR 08/20·08/24·08/25만). 51문서 592행 중 2행(0.3%). 제안: 상한을 `re.search(r"\$[\d,]+", text[end:])`로 찾고 그 앞 텍스트는 자산명에 붙이기, 테스트에 "페이지 넘김 + 상한 분리" 케이스 추가.
  - N-F2B-2(data-engineer): `D:` 설명 라벨이 두 줄로 넘어가면 둘째 줄이 새 chunk가 되어 "no transaction fields" warning → `congress_docs.error = "1 row(s) unparsed"`가 실제 누락 없이 기록되고 설명은 첫 줄에서 잘린다(20035553 "…in San" / "Francisco, CA.", 20035445). 4건의 error 중 2건이 이것. 제안: 라벨 뒤 다음 라벨·거래 필드 전까지의 줄은 마지막 라벨 값에 이어 붙이기.
  - N-F2B-3(data/app): 상태 응답에 "읽지 못한 행 수"가 없다(`congress_docs.error`에만 있음). 화면은 `docs_no_text`(문서 단위)만 말할 수 있다. N-F2B-1·2를 고치면 현재 샘플에서는 0이 되지만, 레이아웃 변화 감지용으로 `rows_unparsed` 합계를 status에 넣기를 권한다.
  - N-F2B-4(data-engineer): 티커가 점 표기로 저장된다(`BRK.B` 3행, `MOG.A` 2행). 앱 심볼은 Yahoo 표기(`BRK-B`)라 보유 종목과 매칭되지 않는다. 저장 시 또는 조회 시 `.`→`-` 정규화(또는 둘 다 비교) 권장. 13F의 `_pick_figi`가 `/`→`-`로 바꾸는 것과 같은 규칙.
  - N-F2B-5(data-engineer, 가설): `_CAP_GAINS = ^[ \t]*(Yes|No|✓)\b`의 `\b`는 ✓ 뒤에 글자가 없으면 성립하지 않아 줄 끝 ✓는 매치되지 않고, ✓·Yes가 다음 줄에 오면 자산명에 붙어 티커가 사라진다(내 입력: 자산명 `Acme Co (ACME)  ✓`, symbol None). 실제 6건 PDF 텍스트에는 Yes/No/✓가 전혀 없고 588행 모두 `cap_gains_over_200=None`. 양식의 체크 표시가 pypdf로 추출되지 않는 글리프라는 가설. 화면은 이 필드에 의존하지 않아야 한다.
  - N-F2B-6(data-engineer, 낮음): `_HEADING`(`^(?:[A-Z]\s+)*[A-Z]\s*$`)이 자산명 줄바꿈으로 생긴 한 글자 줄도 지운다("Alphabet Inc - Class" / "A" / "(GOOGL) [ST]" → 자산명 "Alphabet Inc - Class (GOOGL)", 티커는 유지). 실제 데이터에서는 관찰하지 못함.
  - N-F2B-7(data-engineer, 낮음·가설): 소유자 칸이 비고 자산명이 `SP `·`JT `·`DC `로 시작하면 소유자로 오인한다("SP Plus Corp …" → owner SP, 자산명 "Plus Corp …"). 588행 중 그런 자산명 0건.
  - N-F2B-8(app/data): `POST /api/congress/sync`는 `syncing: true`를 고정으로 돌려주지만 작업은 TTL(24h) 안이면 아무것도 하지 않는다(`test_status_and_manual_sync` 마지막 assert가 이를 고정). 실제 서버는 06:33Z 동기화 뒤 469건 pending인데, 새 배치 반복은 다음 트리거(10-24 06:33Z 이후)에야 돈다. 제안: pending > 0이면 TTL 대신 FAIL_RETRY급 최소 간격만 두거나 수동 엔드포인트는 `force=True`, 응답 `syncing`은 실제 in-flight 여부로.
  - N-F2B-9(리드, docs): CLAUDE.md "TTL 24시간·한 번에 최대 60문서"는 15:53 변경(한 트리거 = 60문서 × 최대 `AM_CONGRESS_MAX_BATCHES`(기본 10) 배치, 1.5초 간격) 전 문구다. `.env.example`에는 설정이 있다. D-030에도 배치 반복 결정이 없다.
  - N-F2B-10(data-engineer, 낮음): fixture 티커 `ACMR`("Acme Rocket Co")는 실제 나스닥 상장 티커(ACM Research)다. 다른 fixture 티커는 가상.
  - N-F2B-11(기록): test_gurus.py는 34→39(새 함수 5개 + `test_guru_list_is_consistent` 확장)로, 리드 메시지의 "+6"과 세는 방식이 다르다. 전체 602 = 직전 598 + 배치 반복·syncing 테스트 4개.
  - N-F2B-12(기록): CIK 17개는 EDGAR 미호출로 독립 확인하지 않았다(UA 미설정, 사용자 이메일 사용 금지). 잘못된 CIK는 `expected_name` 검사로 저장 전에 막히므로 위험은 "표시 안 됨"에 그친다.

### 재현
- backend\에서 `unset VIRTUAL_ENV; py -3.11 -m uv run pytest -p no:cacheprovider` / `py -3.11 -m uv run ruff check .` / `py -3.11 -m uv run ruff format --check .` / `py -3.11 -m uv lock --check`
- `AM_DATABASE_URL=sqlite:///<scratchpad>/f2.db py -3.11 -m uv run alembic upgrade head && alembic heads && alembic check`
- frontend\에서 `unset VIRTUAL_ENV; npm run gen:api; md5sum src/api/openapi.json src/api/schema.d.ts`(재실행 전후 비교)
- 실제 DB 읽기: `py -3.11 -I -c "import sqlite3; c=sqlite3.connect('file:asset_manager.db?mode=ro', uri=True); ..."`(symbol·side·owner 분포, 날짜 순서·금액 위반 count, `congress_docs` status/error)
- 서버(GET만): `curl http://localhost:8001/api/congress/status`, `.../api/congress/trades?symbols=MSFT&days=365`, `.../api/gurus`, `.../api/gurus/norges-bank/holdings?top=3`
- 파서 경계: `PYTHONPATH=. PYTHONIOENCODING=utf-8 py -3.11 -m uv run python <scratchpad>\verify-be\probe_parser.py`
- 실제 PDF 재파싱: `<scratchpad>\verify-be-dl\`에 `curl -A "asset-manager (personal use)" https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/<doc_id>.pdf`로 받은 뒤 `... python <scratchpad>\verify-be\probe_pdfs.py <dl dir>`(라벨 수 vs 행+warning; 누락 행 원문 줄은 `probe_pdfs3.py`)
- grep: `grep -rn "import httpx2\|from pypdf\|import pypdf" app tests`, `grep -rn "<이메일 앞부분>\|@gmail" ...`(0건), `grep -n "live_trading" app/config.py`

### 부록: N-F2B-1·2·4·8 수정 재확인과 최종 수치 (2026-10-23 저녁)
- 판정: **실패(차단 1건). N-F2B-2 수정(라벨 연속 줄 이어 붙이기)이 실제 공시 레이아웃에서 행의 17%를 떨어뜨리고 자산명을 잘라 저장하는 회귀.** N-F2B-1·4·8 수정은 재현해 통과. 전체 pytest·ruff·alembic·프론트 빌드는 통과. 커밋은 파서 수정과 저장된 문서 재파싱 뒤로 미루기를 권한다. 근거는 data-f2b에 보냈고 ISSUE 등록은 담당자가 한다.
- 범위·기준: HEAD ded199d, 작업 트리 해시 `850c19ae…`(`git ls-files -mo --exclude-standard -- backend CLAUDE.md docs/dev scripts | grep -v VERIFICATION.md | sort | xargs md5sum | md5sum`), `congress_provider.py`·`services/congress.py`는 16:34 수정본. 실제 DB·`.env`는 읽기만(`mode=ro`), 8001 서버에는 GET만. 공개 PDF 14건(직전 6건 `verify-be-dl/` + 이번 8건 `verify-be2-dl/`)은 서기국에서 받아 `python -I`로 격리해 파싱했다. 보고에 사용자 보유 종목·금액은 없다(의원 거래 티커는 공개 자료).

#### 전체 점검
| 항목 | 결과 |
|---|---|
| pytest / ruff / format | `py -3.11 -m uv run pytest -p no:cacheprovider` **610 passed**(dot 610개, exit 0. `addopts = "-q"`라 `-q`를 겹치면 요약줄이 없다). `ruff check .` All checks passed, `ruff format --check .` 135 files already formatted |
| alembic | 임시 DB `sqlite:///C:/<scratchpad>/f2final.db` `upgrade head` → `… 6de1dd6fc3d6 → 3af66f72d79b`(congress_trades). `alembic heads` 하나(3af66f72d79b), `alembic check` "No new upgrade operations detected". POSIX `/c/...` 경로는 sqlite가 열지 못해 Windows 경로로 지정해야 한다 |
| gen:api | 재실행 전후 md5 동일(openapi.json `2e0915cc…`, schema.d.ts `90b85696…`) → 작업 트리가 현재 백엔드 스키마와 같다. HEAD 대비 `git diff --stat frontend/src/api/`는 4파일 +703줄(openapi.json 397·schema.d.ts 249는 congress 추가분, client.ts 16·hooks.ts 41은 app 팀원 수정) |
| 프론트 | `npm run build` OK(388ms), `npm run lint`(oxlint) OK, `npm test` **26 files / 150 tests passed** |
| 커밋 후보 | `git status --untracked-files=all`에 `*.db`·`.env`·`artifacts/`·`.vitest/` 없음(`git check-ignore -v`: .gitignore 11·19·24행, frontend/.gitignore 27행). `git diff backend/pyproject.toml`은 `"pypdf>=6.21.2",` 한 줄 추가, `uv.lock` +11줄 `name = "pypdf"` 블록만. 새 untracked `scripts/dev-backend.ps1`(18:03)은 N-F2B-14 |
| 기록 | ISSUES.md 표 45행, 심각도 1+13+21+10=45, 상태 29+12+3+1=45로 합계 줄과 일치. 테스트 수 test_congress.py 20·test_congress_service.py 19·test_congress_api.py 4(ISSUE-045 기재와 일치) |

#### N-F2B-1 (금액 상한을 다음 3줄 안에서 찾기) — 통과, 단서 2
- 내 입력(`verify-be2/probe.py` A): `$250,000`이 `$100,001 -` 줄의 +1·+2·+3번째 줄에 있으면 `amount_high=250000`, +4·+5번째면 "amount upper bound missing" warning으로 행을 보고하고 추측하지 않는다. `_TXN`의 `-\s*`가 첫 줄바꿈을 먹으므로 `after[:tail.start()].count("\n") >= 3`(congress_provider.py:282)이 +4줄부터 거부한다. 페이지 머리글 7줄·`Filing ID #`는 `_is_furniture`로 먼저 빠져 창을 소비하지 않는다(A2: 머리글+자산명 2줄 뒤 상한 → 정상).
- 실제 PDF: 20035491의 DVN 09/02 JT S(partial) `$100,001 - $250,000` 행과 20035390의 LAMR 08/19 SELF S(partial) `$15,001 - $50,000` 행이 이제 파싱된다(직전 검증에서 누락된 2행).
- 단서 ①(data-engineer): **DB에는 두 행이 아직 없다.** 두 문서는 06:33:54Z에 `parsed`로 저장된 뒤 다시 받지 않았고(`fetched_at` 그대로, error `1 row(s) unparsed` 유지), `_run`의 재시도 목록은 `failed`만 담는다(services/congress.py:304). 파서를 고쳐도 `parsed` 문서를 한 번 다시 받는 경로가 없으면 DB는 바뀌지 않는다. N-F2B-2 회귀로 저장된 460문서에도 같은 문제가 적용된다.
- 단서 ②(낮음): 꼬리 탐색은 창 안의 어떤 `$[\d,]+`든 집는다. B: `... S 09/02/2026 09/15/2026 $100,001 -` / `4.5% $1000 par due 2030 (912828XX) [GS] $250,000` → amount `$100,001 - $1000`(high<low), 자산명 끝에 `$250,000` 잔류. ISSUE-045의 "행 시작처럼 보이는 줄은 제외"는 꼬리 탐색이 아니라 라벨 연속 규칙(`_looks_like_row_text`)에만 해당한다. 실제 DB 4,450행에서 `amount_low >= amount_high`는 0건이라 관찰되지는 않았다.

#### N-F2B-2 (`D:` 둘째 줄을 설명에 이어 붙이기) — **실패: 회귀**
- 실제 레이아웃(20035464·20033455 원문 덤프, `probe2.py`): 행 텍스트 → `F S: New` → `S O: <계좌>` → `D: <설명>` → 다음 행. 라벨 셋이 모두 행 **뒤**에 오고 `F S`가 첫 라벨이다. 픽스처 `tests/fixtures/congress/ptr_text_sample.txt`는 `D:`가 `F S:` 앞에 있고(42-44행) `S O:`가 없어 테스트가 실제 순서를 보지 못한다.
- 메커니즘: `F S`에서 flush(congress_provider.py:386-388) → `S O`·`D`가 **다음 행**의 labels에 열림(`open_label`, 390행) → 다음 행 첫 줄이 SELF 소유라 owner 코드가 없고 `[ST]`·거래 필드가 둘째 줄에 있으면 `_looks_like_row_text`(324-331)에 걸리지 않아 라벨 값에 붙는다(392-395). 자산명이 한 줄이면 chunk에 `[ST] P 09/08/2026 ...`만 남아 "asset name missing"으로 행이 사라지고, 두 줄이면 `(GOOG)`·`Stock (MSFT)`처럼 잘린다. 내 입력 C(`D:` 뒤 두 줄 자산명 → 자산명 `(BTAI)`, 설명에 "Beta Industries Class A" 붙음)·C3(`S O:` 뒤 → 같은 현상) 재현.
- 수치(14 PDF, `_looks_like_row_text`를 항상 True로 바꿔 연속 규칙만 끈 결과와 비교): 현재 코드 **624행/133 warning** ↔ 규칙 끔 **751행/8 warning**. 즉 연속 규칙이 **127행(17%)을 떨어뜨리고 394행의 자산명을 자른다.** 문서별(현재 ↔ 규칙 끔): 20035390 50/8 ↔ 58/0(직전 검증 57+1), 20030977 182/42 ↔ 224/0, 20033619 142/36 ↔ 178/0, 20033455 101/20 ↔ 121/0, 20034106 21/12 ↔ 33/0, 20034709 8/6 ↔ 14/0, 20035464 3/2 ↔ 5/0, 20035491 98/1 ↔ 99/0. 모든 문서에서 `F S` 라벨 수 = 행 + warning.
- 실제 DB(07:30Z 소진분 포함 460문서·4,450행, 읽기만): error 있는 문서 **77건, unparsed 합계 351행**, `rows=0`인 parsed 문서 4건. 자산명이 `(`로 시작 **515행**, `Stock (`·`Common Stock (`·`Shares (`·`Class X (`로 시작 **737행**(예 `Stock (MSFT)` 41행, `(AMZN)` 22행, `(NVDA)` 20행). 샘플 8문서의 DB warning 수(42·36·20·12·6·4·1·1)가 현재 코드 재파싱과 정확히 같다 → DB는 현재 파서의 결과다.
- 남은 8 warning: 직전 N-F2B-2 그대로 2건(`D:` 둘째 줄 "Francisco, CA.", 20035445) + 별개 파서 공백 6건(N-F2B-13).
- 부수(기존 동작): `description`은 `F S` flush 뒤에 읽히므로 다음 행에 붙는다(20033455: `D: Ticker 2802 JP`(아지노모토 행의 설명)가 BABA 행에). `CongressTrade`에 description 컬럼이 없어 DB 영향은 없지만 수정 설계 때 함께 봐야 한다.
- 전달한 제안(판단은 담당자): ① 연속 규칙을 되돌리고, flush 시점에 chunk에 거래 필드가 전혀 없고 직전 라벨이 `D`면 설명으로 흡수(가짜 warning 2건 해소) / ② `F S`가 아니라 "다음 행 시작"에서 flush해 `F S`·`S O`·`D`를 앉은 행에 붙이기. 어느 쪽이든 픽스처에 실제 순서(행 → F S → S O → D → owner 코드 없는 두 줄 자산명 행)를 넣고, 저장된 `parsed` 문서를 한 번 다시 받는 경로를 마련할 것.

#### N-F2B-4 (심볼 정규화) — 통과
- 코드: 파싱 시 `normalize_symbol`(congress_provider.py:261-263, `.`·`/`→`-`·upper; 311행에서 적용), 조회 시 `trades()`가 입력을 같은 함수로 정규화(services/congress.py:189), 배치마다 기존 행을 SQL `UPDATE … replace(replace(symbol,'.','-'),'/','-')`(319-330). API `_symbols`도 upper. 내 입력 D: `BRK.B`·`brk/b`→`BRK-B`, ` MOG.A `→`MOG-A`, `BF.B`→`BF-B`, `RDS/A`→`RDS-A`.
- 실제 DB(4,450행): `symbol like '%.%' or like '%/%'` **0건**, 소문자 0건, `[^A-Z0-9-]` 글자 0건. 소진 뒤에도 0.

#### N-F2B-8 (백로그 10분 재시도·실제 `syncing`) — 통과
- 코드: `_is_due`(services/congress.py:218-224) = `error` 없고 `_unfetched`(= `docs_total` − 저장된 doc 전부, 498-501) > 0이면 `min(TTL, BACKLOG_RETRY 10분)`, 실패 문서만 남으면 `_unfetched` 0 → 24h, error면 FAIL_RETRY 1h. `/sync`·`/trades`는 `service.due()`일 때만 `background.add_task`, 응답 `syncing = current.syncing or scheduled`(api/congress.py:85-91, 112-116). `due()`는 `_in_flight`면 False(213-216). 테스트: `test_pending_backlog_resumes_within_the_ttl_after_a_short_pause`, `test_backlog_does_not_shorten_the_retry_after_an_error`, `test_failed_documents_wait_for_the_daily_ttl_not_the_backlog_pause`, `test_status_reports_syncing_while_a_run_is_in_flight`, `test_status_and_manual_sync`(TTL 안·pending 0이면 `syncing False`·provider 호출 없음), `test_manual_sync_resumes_a_pending_backlog_within_the_ttl`.
- 실제 서버: 리드의 17:14 재시작 **전에** 백로그가 이미 소진되어 폴링으로 볼 변화가 없었다. `congress_docs.fetched_at`(배치 시작 시각)으로 복원한 타임라인: 06:33:54Z 60건(첫 배치, 직전 검증 시점) → **07:30:35Z 60 → :42 60 → :47 60 → :51 60 → :56 60 → 07:31:01 60 → :07 60 → :12 49 = 469건, 8배치 약 40초**(배치 간격 4.6~7.0초 = 내려받기+1.5초 pause, 한 트리거의 `_loop`). 최종: docs_total 529, parsed 460, no_text 69(13%, 전부 7자리 DocID), failed 0, pending 0, trades 4,450, synced_at 07:31:12Z. 재시작 뒤 `POST /api/congress/sync`(backend.log 17:15) → 202이지만 synced_at 불변·`syncing false` = pending 0이라 `due()` False로 아무것도 걸지 않은 정상 동작(수정 전에는 `syncing: true`를 고정으로 돌려줬다).
- 30초 간격 폴링(`GET /api/congress/status`):
  - 08:38:28Z(내 첫 GET): syncing false, pending 0, parsed 460, no_text 69, failed 0, trades 4,450, synced_at 07:31:12Z, error null.
  - 10:49:23Z~10:51:39Z 5회(30초 간격): 모두 `WinError 10061` 연결 거부. 11:19Z에도 8001 포트 LISTEN 없음(`netstat`), `backend/.dev-backend*.log` 없음 → 리드 쪽에서 서버를 내린 상태로 보여(가설) 폴링 표본을 얻지 못했다. 최종 수치는 08:38Z 응답과 읽기 전용 DB 집계가 같다(parsed 460·no_text 69·trades 4,450).
- 낮음(코드 읽기, 재현 안 함): `_pending`·`_unfetched`는 `congress_docs` **전체** 수와 365일 창의 `docs_total`을 비교한다. 저장된 문서가 창을 벗어나기 시작하면(약 1년 뒤) 미수신 문서가 `max(…, 0)`에 가려져 0으로 집계될 수 있다. 창 밖 문서를 집계에서 빼거나 지우는 쪽을 권한다.

#### 추가 비차단
- N-F2B-13(data-engineer): 파서가 모르는 금액 표기 — 정확 금액 `$2,000.00`(20033320)·`$2,722.50`(20034999), 라벨 `Spouse/DC Over $1,000,000`(20033695, 4행). "no transaction fields"로 보고되어 조용한 누락은 아니다. 14문서 중 6행.
- N-F2B-14(리드, `scripts/`): `scripts/dev-backend.ps1`(18:03, untracked)이 `backend/.dev-backend.log`·`.dev-backend.err.log`를 만드는데 `.gitignore`에 `*.log` 규칙이 없다(`git check-ignore` 불일치, 파일은 아직 없음). uvicorn 접근 로그에는 `GET /api/congress/trades?symbols=<보유 종목>` 같은 URL이 남으므로 커밋 전에 ignore 규칙을 넣어야 한다.
- N-F2B-15(기록): 날짜 순서 위반 12행(거래일>알림일 또는 알림일>공시일; 예 20030977 UHS 거래 10/23/2025·알림 08/11/2025, 20033889 거래일 2026-12-26). 원문 PDF가 그렇게 적혀 있어(20030977 재파싱에서 동일) 파서 문제가 아니다. 화면은 날짜 순서를 가정하지 말 것.
- N-F2B-3 재강조(data/app): status에 unparsed 행 합계가 없어 이번 351행 누락이 `docs_failed 0 · pending 0`으로만 보였다. `rows_unparsed`(= `congress_docs.error` 합계)를 status에 넣기를 권한다.

#### 재현
- backend\: `unset VIRTUAL_ENV; py -3.11 -m uv run pytest -p no:cacheprovider`(dot 610) / `py -3.11 -m uv run ruff check .` / `py -3.11 -m uv run ruff format --check .`
- `AM_DATABASE_URL=sqlite:///C:/<scratchpad>/f2final.db py -3.11 -m uv run alembic upgrade head && alembic heads && alembic check`
- frontend\: `unset VIRTUAL_ENV; md5sum src/api/openapi.json src/api/schema.d.ts; npm run gen:api; md5sum …; git diff --stat frontend/src/api/; npm run build; npm run lint; npm test`
- 파서: `py -3.11 -m uv run python -I -X utf8 <scratchpad>\verify-be2\probe.py <pdf dir…>`(경계 A·A2, `$` B, 라벨 연속 C·C2·C3, normalize D, 실제 PDF E) / `probe2.py <pdf dir…>`(연속 규칙 on/off 비교, 원문 순서 덤프). PDF는 `curl -A "asset-manager (personal use)" https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{2025|2026}/<doc_id>.pdf`(DocID 2003xxxx 일부는 2025 경로)
- DB 읽기: `py -3.11 -I -X utf8 <scratchpad>\verify-be2\dbread.py`·`dbread2.py`(`file:asset_manager.db?mode=ro`)
- 서버(GET만): `curl http://localhost:8001/api/congress/status`

### 부록 2: 연속 줄 규칙 재설계·REPARSE_BEFORE 재파싱 재확인 (2026-10-26)
- 판정: **통과(차단 0건).** 직전 부록의 차단 1건(N-F2B-2 회귀: 라벨 연속 줄 규칙이 다음 행을 흡수)은 data-f2b의 `parse_ptr_text` 재설계로 해소됐다. 공개 PDF 14건 재측정 **757행 / 0 warning**(목표 ≥751 / ≤8), 자산명이 `(`·`Stock (`로 시작하는 행 **0**(직전 394). 저장된 `parsed` 문서는 `REPARSE_BEFORE`(2026-10-23 10:50Z) 재파싱 경로로 다음 동기화 때 다시 읽힌다(실제 DB 기준 **458건**). 전체 pytest 613·ruff·alembic·gen:api 불변·프론트 빌드/린트/테스트 모두 통과. 비차단 N-F2C-1~7은 아래. ISSUE-045에 이번 회귀·재설계 기록은 **누락**(리드가 적는다).
- 범위·기준: HEAD ded199d 위 작업 트리(`congress_provider.py` 2026-10-23 19:52 KST, `services/congress.py` 21:04 KST 수정본). 실제 DB `backend/asset_manager.db`는 `mode=ro`로 읽기만, `.env`는 열지 않음, 8001 서버는 내려가 있어 띄우지 않았다(실서버 항목은 "서버 중단으로 미확인"). 공개 PDF 14건은 직전 verifier가 받아 둔 `verify-be-dl/`(6)·`verify-be2-dl/`(8)을 그대로 `python -I`로 격리해 파싱했다(새로 내려받은 파일 없음). 사용자 보유 종목·금액은 읽지도 적지도 않았다(의원 거래 티커는 공개 자료).

#### 1. 공개 PDF 14건 전·후 (행/warning)
| 문서 | DB에 저장된 값(구 파서) | 직전 부록 당시 코드 | 연속 규칙 끔(직전 기준) | **현재 트리** |
|---|---|---|---|---|
| 20030977 | 182/42 | 182/42 | 224/0 | **224/0** |
| 20033320 | 0/1 | (0/1) | — | **1/0** |
| 20033455 | 101/20 | 101/20 | 121/0 | **121/0** |
| 20033619 | 142/36 | 142/36 | 178/0 | **178/0** |
| 20033695 | 0/4 | (0/4) | — | **4/0** |
| 20034106 | 21/12 | 21/12 | 33/0 | **33/0** |
| 20034709 | 8/6 | 8/6 | 14/0 | **14/0** |
| 20034999 | 0/1 | (0/1) | — | **1/0** |
| 20035390 | 57/1 | 50/8 | 58/0 | **58/0** |
| 20035434 | 17/0 | (17/0) | — | **17/0** |
| 20035445 | 1/1 | (1/1) | — | **1/0** |
| 20035464 | 5/0 | 3/2 | 5/0 | **5/0** |
| 20035491 | 98/1 | 98/1 | 99/0 | **99/0** |
| 20035553 | 1/1 | (1/1) | — | **1/0** |
| **합계** | 633/126 | 624/133 | 751/8 | **757/0** |
- 괄호는 직전 부록에 문서별 수치가 없어 DB 값으로 대신한 것(DB 값 = 당시 파서 출력이었음을 직전 부록이 확인). 현재가 751보다 6행 많은 것은 N-F2B-13(정확 금액 `$2,000.00`·`$2,722.50`, `Spouse/DC Over $1,000,000` 4행)도 함께 파싱되기 때문이다.
- 불변식: 14문서 모두 `F S` 라벨 수 = 행 + warning(757 = 757 + 0). 자산명이 `(`로 시작 0행, `Stock (`·`Common Stock (`·`Shares (`·`Class X (`로 시작 0행, probe2의 TRUNC 정규식 0행(직전 394). 소문자로 시작하는 자산명 1행(`lululemon athletica inc. - Common Stock (LULU)`, 원문이 그렇다). 설명(`D:`)이 붙은 행 53(= 원문 `D` 라벨 53개). 20033455의 `D: Ticker 2802 JP`가 직전엔 BABA 행에 붙었는데 이제 AJINF(아지노모토) 행에 붙는다(라벨이 앉은 행에 붙음).
- 라벨 종류(14 PDF, 머리글 제거 뒤): `FS` 757·`SO` 734·`D` 53·`L`(Location, 예 `L: US`) 4. 값이 빈 라벨 0건. `L`은 `_FREE_TEXT_LABELS`에 없어 한 줄 값으로만 처리되며 실제 문서에서 모두 한 줄이었다.
- 픽스처: `ptr_text_sample.txt`(실제 순서 행 → F S → S O → D → owner 코드 없는 두 줄 자산명 행, 문서 끝 두 줄 `D:`) 8행/0 warning, r8 설명이 "… in San Francisco, CA."로 합쳐짐. `ptr_text_legacy.txt`(F S 없음) 2행. 내 입력(`verify-be3/probe3_inputs.py` 14종): `S O`/`D` 뒤 SELF 두 줄 행(직전 회귀 케이스) → 행·자산명 보존; `D` 둘째 줄이 문서 끝 → 설명에 합침; 문서 끝 `D` 뒤 거래 필드 없는 줄은 설명으로 흡수되고 `S O` 뒤면 warning(설계대로); 첫 행 앞 고아 라벨 → 무시; 한 행에 `D` 둘(뒤가 덮어씀); `F      S     : Amended` 인식.
- 알려진 한계(TODO_FOR_ME 44행과 일치): `D:`가 문서 **중간**에서 두 줄이면 둘째 줄 조각이 다음 행 자산명 앞에 붙는다(`Francisco, CA. Beta Industries Class A (BTAI)`, 티커 보존). 14 PDF에서 0건(자유 텍스트 라벨 다음 줄이 소문자로 시작하는 경우 0). `S O :` 값이 비고 계좌명이 다음 줄에 오면 다음 행 자산명 앞에 붙는다(내 입력 #6) — 실제 문서에서 빈 값 라벨 0건.

#### 2. 재파싱 경로(`REPARSE_BEFORE`) — 통과
- (a) due: `_to_reparse(now)`(services/congress.py)는 `now < reparse_before`면 0, 지나면 `status='parsed' and fetched_at < reparse_before and filing_date >= now − lookback`인 문서 수. `_is_due`는 `error`가 없고 `_unfetched > 0 or _to_reparse > 0`이면 `min(TTL, BACKLOG_RETRY 10분)`. 테스트 `test_documents_parsed_before_a_parser_change_are_read_again_once`(마감 10분 전 due False → 지나면 True) + 내 시뮬레이션(`verify-be3/sim_reparse.py`, 메모리 DB·Fake provider): 마감 전 3회 배치 뒤 마감+1분에 `to_reparse=4, due=True`.
- (b) 교체: `_store`가 같은 트랜잭션에서 `delete(CongressTrade where doc_id)` 뒤 `add_all`, `_run` 끝의 `commit()` 한 번. 시뮬레이션: 문서 100의 행이 `[(0,'BBB'),(1,'CCC')]`로 바뀌고 `(doc_id,row_no)` 중복 0. 테스트 `test_reparsing_a_document_replaces_its_rows_without_duplicates`(failed 경로)·위 테스트(reparse 경로, ZYXW 행 소멸).
- (c) 한 번만: `_upsert_doc`가 `fetched_at = now`(배치 시작 시각, `stale()`이 `now >= reparse_before`를 요구하므로 마감 이후). 시뮬레이션: 재파싱 뒤 `to_reparse=0`, `due=False`, +10분·+25시간(테스트) 모두 문서 호출 없음. 색인에서 사라진 stale 문서는 `fetched_at=now`로 표시해 10분마다 헛도는 것을 막는다(테스트의 D 문서).
- (d) `no_text`·`failed`: `stale()`은 `status == parsed`만 보므로 `no_text`는 그대로(시뮬레이션 103의 `fetched_at` 09:10 유지), `failed`는 종전처럼 `retry` 목록(daily TTL). 변경 없음.
- (e) `/api/congress/status`의 `docs_pending`: **재파싱 잔량을 포함하지 않는다.** `status()`는 `_pending(total, counts)` = total − (parsed + no_text)만 쓰고, `reparse_left`는 `SyncResult.docs_pending`에만 더해진다(`_run`). 시뮬레이션: 마감 뒤 `status.docs_pending=1`(failed 1건)인데 `to_reparse=4`. 동기화 자체는 `due()`로 `/trades`·`/sync`가 배경 작업을 걸어 `syncing: true`를 돌려주므로 진행된다. 비차단 N-F2C-1.
- 실제 DB(읽기만): parsed 460·no_text 69·failed 0, `fetched_at` 전부 2026-10-23 06:33~07:31Z(< 10:50Z) → `fetched_at ≥ 10:50Z`인 parsed 문서 **0**. 365일 창(2026-10-26 기준 `filing_date ≥ 2025-10-26`) 안 **458건**이 다음 동기화 때 다시 읽힌다(60건×최대 10배치 = 600 ≥ 458이라 한 트리거로 끝남). `filing_date` 2025-10-23~25인 2건은 창 밖이라 다시 읽지 않고 구 파서 행이 남는다(N-F2C-3). 지금 DB의 자산명 `(` 시작 515행·`Stock (`류 729행, error 문서 77건·unparsed 351행이 재파싱 대상이다.
- 설계 판단(비차단): 시각 상수는 단일 사용자 로컬 앱에서 충분하다. 모든 문서에 `fetched_at`이 있고(NULL 0), UTC naive로 일관되며, 재파싱은 수렴한다. 부담·위험: ① 파서를 바꿀 때마다 상수를 손으로 올려야 하고 잊으면 조용히 구 결과가 남는다(TODO_FOR_ME 44행에 절차 기록). ② `REPARSE_BEFORE`(10:50:00Z)가 `congress_provider.py` 최종 수정 시각(19:52:54 KST = 10:52:54Z)보다 약 3분 이르다 — 그 사이 구 코드로 파싱된 문서는 다시 읽히지 않는데, 서버가 내려가 있어 DB에 그런 문서는 0건이다. ③ `parser_version` 컬럼이면 자기 설명적이고 시계와 무관하지만 마이그레이션이 필요하다. 지금은 상수로 두고, 파서를 또 바꾸면 상수를 "수정 커밋 시각 이후"로 올리는 규칙만 지키면 된다.

#### 3. 전체 점검
| 항목 | 결과 |
|---|---|
| pytest | `py -3.11 -m uv run pytest -p no:cacheprovider` **613 passed**(128초, exit 0; 직전 610 → test_congress.py 20→22, test_congress_service.py 19→20, test_congress_api.py 4) |
| ruff | `ruff check .` All checks passed / `ruff format --check .` 135 files already formatted |
| alembic | 새 스크래치 DB `sqlite:///C:/<scratchpad>/verify-be3/f2c.db` `upgrade head` → `… 6de1dd6fc3d6 → 3af66f72d79b`, `heads` 단일 `3af66f72d79b (head)`, `check` "No new upgrade operations detected"(마이그레이션 없음 = 스키마 불변) |
| gen:api | 재실행 전후 md5 동일(openapi.json `2e0915cc…`, schema.d.ts `90b85696…`, 직전 부록과도 같음). `git status --short frontend/src/api`는 HEAD 대비 M 4건(+703줄, F-2 추가분 그대로)이고 gen:api로 새로 바뀐 것은 없다 |
| 프론트 | `npm run build` OK(1.03s), `npm run lint`(oxlint) OK, `npm test` **26 files / 150 tests passed** |
| 실서버 | 8001 중단 상태라 `/api/congress/status`·재파싱 진행은 **서버 중단으로 미확인**. 사용자가 `.\scripts\dev-backend.ps1`로 띄우면 첫 `/trades` 또는 `/sync`에서 458건 재파싱이 한 트리거로 돈다(약 8배치, 직전 부록 기준 40초 안팎) |

#### 4. 커밋 후보·공개 저장소
- `git status --short --ignored`: 커밋 후보(M 27·?? 14)에 `*.db`·`.env`·`backend/artifacts/`·`frontend/.vitest/`·`backend/.dev-backend*.log`·`.claude/` 없음. ignored(`!!`)로 `backend/asset_manager.db(-shm/-wal)`·`demo.db`·`backend/.env`·`backend/artifacts/`·`frontend/.vitest/`·`frontend/dist/`·`.claude/` 확인. `.gitignore` diff는 `backend/.dev-backend*.log` 규칙 추가(N-F2B-14 해소)와 `.claude` 줄 끝 개행만.
- `git diff backend/pyproject.toml` = `"pypdf>=6.21.2",` 한 줄, `uv.lock` +11줄 `pypdf 6.21.2` 블록만.
- 개인정보 grep(M·?? 전부 + `docs/dev/*.md` + CLAUDE.md): 이메일 패턴·`@gmail`·이메일 앞부분·git 사용자명 0건(VERIFICATION.md의 "grep 결과 0건" 문구 자체만 매칭). 원화 금액 패턴은 ISSUES.md 354행(S2 백테스트 합성 평가액)과 VERIFICATION.md 544행(포맷 함수 예시)만으로 보유 데이터가 아니다. `backend/.env.example`은 전부 빈 값·주석 자리표시자(`AM_LIVE_TRADING=false` 포함). `scripts/dev-backend.ps1`에 연락처·키 없음. `congress_provider.USER_AGENT = "asset-manager (personal use)"`(`@` 없음, 테스트가 고정).
- `AM_LIVE_TRADING`: 이번 변경 파일에 등장 없음(`.env.example` 기본 false 그대로).

#### 5. 기록 점검
- `docs/dev/ISSUES.md` ISSUE-045(470~475행, 2026-10-23 17:08 수정본): "라벨 연속 줄을 값에 이어 붙임"까지만 적혀 있고, 이 규칙이 실제 순서(행 → F S → S O → D)에서 다음 행을 흡수한 회귀(직전 부록 N-F2B-2)와 해결(`open_label` 재설계: 라벨은 앉은 행에, 자유 텍스트 둘째 줄은 문서 끝에서만 합침 + `REPARSE_BEFORE` 재파싱)은 **누락**. "검증" 줄의 테스트 수(20·19·4, 610)도 현재(22·20·4, 613)와 다르다. `REPARSE_BEFORE`·재파싱 언급은 ISSUES/DECISIONS/PROGRESS에 없고 TODO_FOR_ME 44행에만 있다.
- 표: 45행, 심각도 치명 1·높음 13·중간 21·낮음 10, 상태 미해결 29·해결/부분 12·보류 3·결정됨 1로 합계 줄(65행)과 일치.

#### 비차단
- N-F2C-1(data-engineer, 중간): `CongressStatus.docs_pending`에 재파싱 잔량이 없다. 화면은 `docs_pending > 0`으로 "N건 더 받는 중"과 수동 받기 버튼(`CongressTrades.tsx` 31·101행)을 판단하므로 458건 재파싱 중에도 0으로 보인다(폴링은 `syncing`으로 계속된다). `status()`의 `_pending(...)`에 `_to_reparse(now)`를 더하거나 별도 필드(`docs_to_reparse`, 스키마 변경이면 `gen:api`)를 권한다. N-F2B-3(`rows_unparsed`)과 묶어 처리하면 좋다.
- N-F2C-2(data-engineer, 낮음, 기존 동작): `batch = (fresh + retry + reparse)[:max]`라서 백로그(신규 또는 재파싱)가 남아 있는 동안 `failed` 문서는 **매 배치마다** 다시 받는다(시뮬레이션: 한 트리거 5배치에서 104를 5번 호출, `docs_failed` 합계 5). 실제 DB는 failed 0이라 지금 영향은 없다. retry는 트리거당 한 번만 넣는 것을 권한다.
- N-F2C-3(data-engineer, 낮음): `REPARSE_BEFORE` 10:50:00Z < 파서 파일 최종 수정 10:52:54Z(위 ②). 또 `filing_date`가 365일 창 밖인 parsed 2건(2025-10-23~25)은 다시 읽히지 않아 구 파서 행이 `congress_trades`에 남는다(API 기본 180일 창에는 안 보임).
- N-F2C-4(리드, 기록): ISSUE-045에 회귀·재설계·`REPARSE_BEFORE` 추가, 테스트 수 갱신. 재파싱 설계(시각 상수 vs `parser_version`)는 DECISIONS에 한 줄 남기길 권한다.
- N-F2C-5(data-engineer, 낮음, 기록됨): 문서 중간 두 줄 `D:` 조각이 다음 행 자산명 앞에 붙는 한계(TODO 44행). 빈 값 `S O :`도 같은 경로. 두 경우 모두 14 PDF에서 0건.
- N-F2C-6(기록): `parse_amount("$2,000.00")` = (2000, 2000)이라 정확 금액 행은 `amount_low == amount_high`다(20033320 ANGO). 직전 부록의 "low ≥ high 0건" 불변식은 재파싱 뒤 이 1행으로 깨지며 버그가 아니다.
- N-F2C-7(app-engineer, 낮음): `CongressStatusOut.docs_pending` 설명("Still to download")과 `SyncResult.docs_pending`("including documents still to re-read")의 뜻이 달라졌다. N-F2C-1과 함께 정리.

#### 재현
- 스크래치: `C:\Users\user\AppData\Local\Temp\claude\c--Users-user-Desktop-project\390c67f2-c016-4b04-a641-dbd27eed466f\scratchpad\verify-be3\` — `probe3.py`(14 PDF 행/warning/`(`·`Stock (`·TRUNC/설명/low≥high, 출력 `probe3_out.txt`), `probe3_inputs.py`(내 입력 14종 + 픽스처 2종), `probe4.py`(라벨 종류·빈 값·소문자 시작 자산명), `probe5.py`(`L` 라벨 문맥), `sim_reparse.py`(메모리 DB 재파싱 시뮬레이션), `dbread3.py`(실제 DB `mode=ro` 집계), `pytest_full.log`, `frontend_chain.log`, `f2c.db`.
- backend\: `unset VIRTUAL_ENV; py -3.11 -m uv run python -I -X utf8 <scratch>\verify-be3\probe3.py <scratch>\verify-be-dl <scratch>\verify-be2-dl`(probe2.py는 삭제된 `_looks_like_row_text`를 참조해 현재 트리에서 돌지 않아 사본을 새로 썼다) / `… probe3_inputs.py` / `… probe4.py <pdf dirs>` / `… sim_reparse.py` / `py -3.11 -I -X utf8 <scratch>\verify-be3\dbread3.py`
- `py -3.11 -m uv run pytest -p no:cacheprovider` / `ruff check .` / `ruff format --check .` / `AM_DATABASE_URL=sqlite:///C:/<scratch>/verify-be3/f2c.db py -3.11 -m uv run alembic upgrade head && alembic heads && alembic check`
- frontend\: `unset VIRTUAL_ENV; md5sum src/api/openapi.json src/api/schema.d.ts; npm run gen:api; md5sum …; git status --short src/api; npm run build; npm run lint; npm test`
- 공개 PDF가 없을 때: `curl -A "asset-manager (personal use)" https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{2025|2026}/<doc_id>.pdf`(문서 id는 위 표)

#### 부록 2 추가: N-F2C-1·3·7 후속 수정 확인 (2026-10-26)
- 판정: **통과(차단 0건).** data-f2c가 f943ca5 위 작업 트리에 남긴 후속 수정 3건(N-F2C-1·3·7)은 주장과 같고 그 이상이 없다. 새 테스트는 구 코드에서 실제로 실패하는 값을 고정한다. 실서버의 458건 재파싱은 끝났다.
- 범위: HEAD f943ca5 + `git status --short` M 4건(`backend/app/services/congress.py` +39/−14, `backend/app/schemas/congress.py` +3, `backend/tests/test_congress_service.py` +36, `docs/dev/ISSUES.md` 1줄). 그 외 M·?? 없음(gen:api 재실행 뒤에도 같음). 실제 DB `backend/asset_manager.db`는 `mode=ro`로 읽기만, 8001 서버는 GET만, `.env`는 열지 않음.

##### 1. diff 대조 — 통과
| 주장 | 확인 |
|---|---|
| N-F2C-1 `status().docs_pending = _pending_now(total, counts, now)` = `_pending + _to_reparse(now)` | 일치. `status()`는 이미 계산한 같은 `now`를 넘긴다. `_skipped(sync, now)`(시그니처에 `now` 추가, `sync()`의 두 호출 모두 갱신)와 `_run`의 색인 실패 경로(`SyncResult(True, 1, 0,0,0,0, pending, message)`)도 `_pending_now`. |
| `_run` 성공 경로 불변 | 일치: `docs_pending=_pending(len(due), counts) + reparse_left` 그대로(diff에 hunk 없음). |
| `_loop` 종료 조건 불변 | 일치: `if result.error or result.docs_pending == 0 or progress == 0: break` 그대로. 색인 실패 경로는 `error`가 있어 어차피 첫 조건에서 멈추므로 `docs_pending` 값 변화가 반복 횟수에 영향 없음. |
| N-F2C-3 `REPARSE_BEFORE` 10:50 → 11:00 | 일치. 파서 파일 `congress_provider.py` mtime(UTC) `2026-10-23 10:52:54.298` < 11:00. 실제 DB에서 `fetched_at`이 10:50~11:00 사이인 parsed 문서 **0**이라 상수 이동으로 재파싱 대상이 바뀐 문서는 없다. |
| N-F2C-7 주석 통일, `Field(description=...)` 불변 | 일치. `schemas/congress.py` diff는 `#` 주석 3줄만, `docs_pending: int = Field(description="Still to download; a first sync works in batches")` 그대로(아래 gen:api 불변으로 재확인). `CongressStatus`·`SyncResult`의 `docs_pending` 주석은 같은 한국어 문장. |
| 새 테스트 1건 | `test_status_counts_documents_waiting_for_a_re_parse_as_pending` 추가만(+36줄), 기존 테스트 변경 없음. |

##### 2. 테스트·린트 — 통과
| 항목 | 결과 |
|---|---|
| pytest | `py -3.11 -m uv run pytest -p no:cacheprovider` **614 passed**(118.8초, exit 0; 직전 부록 613 → +1 = 새 테스트). `pyproject.toml` `addopts = "-q"` 때문에 요약 줄이 파이프 `tail`에 안 잡혀 로그 파일로 확인(`verify-be4\pytest_full.log`). |
| 콩그레스 | `-o addopts="" --collect-only -q`: `test_congress_service.py` **21**, `test_congress_api.py` **4**, `test_congress.py` 22 → 세 파일 47 passed(2.2초). data-f2c 주장 21·4와 일치. |
| ruff | `ruff check .` All checks passed / `ruff format --check .` 135 files already formatted |
| gen:api | `VIRTUAL_ENV` 때문에 `npm run gen:api` 대신 직접 체인: backend `py -3.11 -m uv run python -m app.export_openapi ../frontend/src/api/openapi.json` → frontend `npx --yes openapi-typescript@7 src/api/openapi.json -o src/api/schema.d.ts`(7.13.0). 전후 md5 동일(openapi.json `2e0915cc…`, schema.d.ts `90b85696…`, 직전 부록과도 같음), `git status --short frontend/src/api` **비어 있음**. |

##### 3. 새 테스트가 회귀를 잡는가 — 통과
- 테스트 본문 논리: 첫 sync(`max_batches=1`, 20038002 실패) 뒤 `docs_total=4`(A·B·C·D, E는 창 밖, F 비PTR, G 날짜 없음), counts parsed 2·no_text 1·failed 1 → `_pending`=1. 이어 20039001·20037001·9001234의 `fetched_at`을 `REPARSE_BEFORE − 1h`로 되돌리면 `_to_reparse(NOW=12:00)`는 parsed 2건(no_text 9001234는 제외)이라 새 식 **3**, 구 식(`_pending`만) **1**. 단언 `(docs_pending, docs_parsed, docs_failed) == (3, 2, 1)`은 구 코드에서 `(1, 2, 1)`로 실패한다. `skipped.docs_pending == 3`도 구 `_skipped`에서는 1. `lookback=300d`의 2(20037001 filing 2025-11-01 제외)는 `docs_total`이 sync 행의 4로 고정된 채 `_to_reparse`만 줄어드는 것을 확인한다. 끝의 `due()`·호출 순서 `["20038002","20039001","20037001"]`·`(0, 3, 0)`·`not due()`는 재파싱이 한 번만 돌고 daily TTL로 돌아감을 고정.
- 시뮬레이션(코드 수정 없이 메모리 DB에서 모듈 함수 `_pending`·`_to_reparse`를 함께 출력, `verify-be4\sim_status.py`): ① 첫 sync 뒤 `status=1 / 구 _pending=1 / _to_reparse=0` ② 되돌린 뒤 **`status=3 / 구 _pending=1 / _to_reparse=2`**, skipped sync `docs_pending=3`, lookback 300d → 2 ③ +10분 `due()=True`, 호출 `['20038002','20039001','20037001']`, 결과 parsed 3·pending 0, 이후 `status=0 / 구 0 / 재파싱 0`, `due()=False`. 구 식과 새 식이 2단계에서 갈라지므로 `_pending_now`를 `_pending`으로 되돌리면 테스트가 실패한다.

##### 4. 실서버·실제 DB(읽기만) — 재파싱 완료
- `GET http://localhost:8001/api/congress/status`(구 코드로 실행 중): `synced_at 2026-10-26T00:47:17Z`, `index_modified 2026-10-23T13:00:28`, `stale false`, `syncing false`, `error null`, `docs_total 528`, `docs_parsed 462`, `docs_no_text 69`, `docs_failed 0`, `docs_pending 0`, `trades 4804`.
- DB `congress_docs`: parsed 462 = `fetched_at ≥ 2026-10-26` **460**(모두 00:47:17Z 한 트리거) + `fetched_at < 2026-10-23 11:00` 2(filing 2025-10-23~25, 365일 창 밖 → 설계상 재파싱 대상 아님, N-F2C-3 후반 그대로). no_text 69는 전부 2026-10-23(재파싱 안 함, 설계대로). 일별 히스토그램 `2026-10-23: no_text 69·parsed 2 / 2026-10-26: parsed 460`. `error`(unparsed 행 메모) 있는 parsed 문서 **1**(직전 77).
- DB `congress_trades`: 총 **4804**, `fetched_at ≥ 2026-10-26` 4803, 구 파서 행 1(창 밖 문서), 자산명 `(`로 시작 **0**(직전 394), `Stock (`로 시작 0, 심볼에 `.`·`/` 0, 문서 없는 고아 행 0. 행 수 상위 심볼은 MSFT·AAPL·GOOGL·NVDA·HD 순(공개 PTR 집계).
- 새 코드 `status()`를 실제 DB에 `mode=ro`로 직접 실행(`verify-be4\status_real.py`): `docs_pending 0`, `_to_reparse(now) 0`, `due() False` → 리드가 서버를 새 코드로 재시작해도 추가 재파싱·10분 재시도는 생기지 않고 화면 숫자도 구 코드와 같다(백로그가 없을 때 두 식이 같음).

##### 5. 기록 — 통과
- `git diff docs/dev/ISSUES.md`: ISSUE-045 "회귀 검증(2026-10-26, verifier 부록 2)" 줄 끝에 "N-F2C-1은 `status().docs_pending`에 재파싱 잔량을 더해 해결(2026-10-26)." 한 문장 추가만(+1/−1, 다른 줄 없음).

##### 비차단
- N-F2C-3 후반(낮음, 기존 기록): 365일 창 밖 parsed 2건의 구 파서 행 1건은 `congress_trades`에 남는다(API 기본 180일 창에는 안 보임). 이번 수정 범위 밖.
- `status()`가 호출마다 `_to_reparse` COUNT 쿼리 1개를 더 한다(인덱스 있는 작은 표, 무시 가능).

##### 재현
- 스크래치 `C:\Users\user\AppData\Local\Temp\claude\c--Users-user-Desktop-project\390c67f2-c016-4b04-a641-dbd27eed466f\scratchpad\verify-be4\`: `sim_status.py`(메모리 DB 회귀 시뮬레이션), `status_real.py`(새 `status()`를 실제 DB `mode=ro`로), `dbread4.py`(sqlite3 `mode=ro` 집계), `pytest_full.log`, `pytest_congress.log`, `appendix.md`.
- `git status --short && git diff` / backend\: `py -3.11 -m uv run pytest -p no:cacheprovider > <scratch>\verify-be4\pytest_full.log 2>&1; tail -n 3 …` / `py -3.11 -m uv run pytest -o addopts="" --collect-only -q tests/test_congress_service.py` / `ruff check .` / `ruff format --check .` / `py -3.11 -m uv run python -X utf8 <scratch>\verify-be4\sim_status.py` / `… status_real.py` / `py -3.11 -I -X utf8 <scratch>\verify-be4\dbread4.py`
- gen:api: backend\ `unset VIRTUAL_ENV; py -3.11 -m uv run python -m app.export_openapi ../frontend/src/api/openapi.json` → frontend\ `npx --yes openapi-typescript@7 src/api/openapi.json -o src/api/schema.d.ts; md5sum src/api/openapi.json src/api/schema.d.ts; git status --short src/api`
- 실서버: `curl -s http://localhost:8001/api/congress/status` / 파서 mtime: `TZ=UTC stat -c '%y %n' backend/app/data/congress_provider.py`
- 비고(줄 끝): 이 파일은 git에 LF로 저장된다(HEAD CR 0개, `.gitattributes` `* text=auto eol=lf`, `core.autocrlf=true`). 작업 트리는 588행부터 CRLF(이전 세션 기록)이고 이번 부록 45줄도 CRLF로 붙였다. 커밋 시 git이 LF로 정규화하므로 `git diff --stat`은 +45 삽입만 보인다. MSYS `sed`/`grep`은 읽을 때 CR을 떼므로 줄 끝 확인은 `xxd`·`tr -cd`로 한다.

### 종목 상세 차트 툴팁: 일자별 고가·저가·전일 대비 (2026-10-26)

대상: app-engineer의 미커밋 변경(수정 12 파일 +327/−40, 신규 `BarReadout.tsx`·`BarReadout.test.tsx`·`CandleChart.test.tsx`). 리드가 브라우저에서 찾은 "캔들 읽기판이 캔버스 아래에 깔림"(ISSUE-046)의 `z-10` 수정까지 포함한 최종 상태를 검증했다. 브라우저 확인은 리드.

**판정: 통과**(반박 실패). 백엔드·`openapi.json`·`schema.d.ts` 변경 없음(`git status --short -- backend frontend/src/api` 비어 있음, `BarOut`에 `high`·`low`가 이미 있음).

#### 재현(절대 경로, bash, `unset VIRTUAL_ENV`)
| 시점 | 명령 | 결과 | 보고 |
|---|---|---|---|
| 1차(z-10 전, 15:17) | `npm run build && npm run lint && npm test` | build exit 0 · oxlint exit 0(0건이면 출력 없음) · vitest **27 files / 165 tests** | 27/165 일치 |
| 2차(최종, 15:26:59 시작 — `CandleChart.tsx` 15:23:11·`CandleChart.test.tsx` 15:24:18 수정 뒤) | 같음 | build exit 0 · lint exit 0 · vitest **28 files / 167 tests**(4.27초) | 28/167 일치 |
| 테스트 증분 | `git show HEAD:<test> \| grep -cE '^\s*(it\|test)\('` vs 작업 트리 | HEAD 150 → 167 = **+17**(PriceForecastChart +4, ui +1, format +1, priceChart +6, BarReadout 3, CandleChart 2) | 1차 보고 "+18"은 실제 +15. 최종 숫자는 일치하므로 비차단 |
| 줄 끝 | `git ls-files --eol`(수정 12) / `grep -c $'\r'`(신규 3) | 모두 `w/lf` / CR 0 | — |

#### 확인한 항목
| 항목 | 확인 |
|---|---|
| `buildRows` 첫 봉 | `prev = i > 0 ? bars[i-1].close : prevClose`. `prevClose` 없으면 `closeChange`가 `undefined`를 돌려 스프레드로 `change`·`changePct` 키 자체가 없다(0으로 보이지 않음). 하락일 음수(테스트 `-1`, `-4/104`), `up`은 같은 `prev`로 판단해 `change` 부호와 일관(`withPrev.up === false`). |
| 예측 행 % 기준 | `midPct = pctFrom(anchor, p50·anchor/base) = (p50/base − 1)·100`. 스케일 `k`가 약분되어 통화·진행 중 봉과 무관하고, `ForecastPanel.tsx:176`의 `move = (h.p50/h.base_price − 1)*100`과 같은 수. "마지막 종가 대비" 라벨과 일치. |
| 정직성(예측) | `PriceTooltipContent`는 `row.close === undefined`일 때만 예측 분기이고 거기엔 `formatPct(v, true, 1)` 문자열 `TipRow`만 있다. `PnL`은 과거 분기에만 쓰인다. 테스트가 예측 행에 `[▲▼]` 없음·`.text-gain, .text-loss` 없음·`고가`·`전일 대비` 없음을 단언. 마지막 봉(띠 시작점, `mid`·`band` 있음)은 `close`가 있어 거래일로 표시된다. |
| 정직성(과거) | `PnL` → `changeMark(direction)`(단일 출처) + `signed()`: 부호·▲▼·`text-gain/text-loss` 셋 다 나온다(`▼−4원(−3.85%)`, `▲+2원(+2.00%)`). `BarReadout`도 같은 `PnL`. 홈·헤더도 `PnL`을 쓰므로 어긋남 없음. `NewsCard`의 ▲▼는 뉴스 감성 표시(대비 수치 아님). |
| 통화 | 두 차트 모두 `AssetDetail`의 `useMoney().format`을 prop으로 받아 그대로 쓴다. 원화 재계산 없음. `prevClose = bars[from-1].close`는 `scale`을 곱한 배열에서 꺼내므로 보이는 봉과 같은 통화이고 memo 의존성에 `scale` 포함. |
| `priceDomain` 허용 목록 | `close/mid/band/ma*`만 — 기존 키 집합에서 제외 규칙(`t/volume/up`)을 뒤집은 것과 동치. 새 키(`open/high/low/change/changePct/midPct/bandPct`)는 축에 안 들어간다. 기존 `priceChart.test.ts` 11건 변경 없이 통과(17건으로 추가만), 평균단가·52주 extras 경로 변경 없음. |
| `CandleChart` 콜백 | `onCrosshair`는 `candle`(차트 수명 동안 고정된 const)과 `setHoverDate`만 캡처 → stale closure 없음. `bars`는 렌더에서 읽는다. 정리 함수가 `unsubscribeCrosshairMove` 뒤 `chart.remove()`. 빈 `seriesData`(마우스 이탈) → `null` → 마지막 봉, `hoverDate`가 `bars`에 없으면(기간 변경) 마지막 봉. 같은 문자열이면 React가 재렌더를 생략. |
| `timeKey` | lightweight-charts 5.2.1 typings: `seriesData` "Values of the map are original data items" → 우리가 넣은 `'YYYY-MM-DD'` 문자열이 그대로 온다. 문자열·BusinessDay 둘 다 처리(테스트). 숫자(UTCTimestamp) 분기는 현재 쓰이지 않는 경로. |
| 첫 봉 거래량 색 | 캔들 `volumes`도 `prev = i > 0 ? … : prevClose`로 선 보기 `up`과 같은 기준. 의존성에 `prevClose` 추가. |
| ISSUE-046 `z-10` | 번들에 `zIndex = '1'` 3곳·`'2'` 3곳(절대 배치 캔버스). dist CSS에 `.z-10{z-index:10}`, `bg-surface/85` → `color-mix(in oklab, var(--surface) 85%, transparent)` 생성 확인(Tailwind 4.3.3). 새 테스트가 `z-10`·`pointer-events-none`을 고정. |
| 색 | 변경 파일에 `#rrggbb` 리터럴 없음(`translucent` 정규식만, 기존). 토큰 클래스·CSS 변수만. `console.`·`debugger` 없음. |
| 합성 데이터 | 테스트 값은 99/104/98/101, 2026-10-19~21, 거래량 1,000·25,000,000 등 합성값. 실제 보유 종목·수량·금액 없음. |
| 기록 | CLAUDE.md 한 문장(툴팁·읽기판·`prevClose`·예측 날 부호만) 코드와 일치. `DECISIONS.md` D-031은 리드 작성. |

#### 발견한 문제
- ISSUE-046(리드가 브라우저에서 발견, app-engineer `z-10`으로 수정, verifier는 번들·dist CSS·테스트로 확인). 그 외 차단 문제 없음.

#### 비차단
- 1차 보고의 "+18 tests"는 실제 +15(최종 +17). 최종 27→28 files / 165→167 tests는 보고와 일치.
- `timeKey`의 숫자 분기는 `toISOString()`(UTC 날짜)이라 UTCTimestamp를 쓰게 되면 로컬 날짜와 어긋날 수 있다. 지금은 문자열만 넣어 dead path.
- D-031에 실제 포트폴리오의 손실 확률(55~60%)·변동성(연 40~50%) 범위가 적혀 있다. 종목·수량·금액은 아니라 규칙 안이지만 공개 저장소 기준은 리드 판단.
- 보합(변동 0)인 날은 `PnL`이 중립·화살표 없음인데 거래량 막대는 `>=` 규칙으로 상승색. 기존 규칙이고 이번 변경이 만든 것 아님.
- 업비트 코인 거래량(코인 단위, 소수)이 `formatKrwCompact`로 `1,234.568`·`만` 단위로 보인다. 선 보기 툴팁의 기존 동작이 읽기판에도 그대로 옴. 표기 문제.

#### 재현 명령
- `cd /c/Users/user/Desktop/project && git status --short && git diff --stat && git status --short -- backend frontend/src/api`
- `cd /c/Users/user/Desktop/project/frontend && unset VIRTUAL_ENV && npm run build && npm run lint && npm test`
- `git ls-files --eol <수정 파일>` / `grep -c $'\r' <신규 파일>`
- `grep -oE "\.z-10\{[^}]*\}|\.bg-surface[^{]*\{[^}]*\}" frontend/dist/assets/*.css` / `grep -oE "zIndex = '[0-9]+'" frontend/node_modules/lightweight-charts/dist/lightweight-charts.development.mjs | sort | uniq -c`
- 로그: 스크래치 `fe_run.log`(1차)·`fe_run2.log`(2차).

### 가져오기 직접 입력 (2026-10-26)

대상: app-engineer의 미커밋 변경(D-032): 백엔드 `api/imports.py`·`schemas/imports.py`·`services/statement_import.py` + 신규 `tests/test_imports_manual.py`, 프론트 `Import.tsx`·`client.ts`·`hooks.ts`·`App.tsx`·`openapi.json`·`schema.d.ts` + 신규 `Import.test.tsx`, CLAUDE.md·DECISIONS.md. 브라우저 확인은 리드가 한다.

**판정: 통과**(반박 실패). 차단 문제 없음. 비차단: ISSUE-047(거래 메모 출처 문구) 1건 + 문서 표현 1건 + 데모 모드 관찰 1건.

#### 범위
| 확인 | 결과 |
|---|---|
| `git status --short` | 수정 11 + 신규 2. 백엔드는 보고한 3개 파일 + 테스트 1개뿐. `backend/app/deps.py`·`backend/app/services/transactions.py`는 목록에 없음(변경 없음) |
| `git diff --stat` | 11 files, +684/−118. `statement_import.py` +127(`preview_manual`·`_manual_row`·`_held`·`_quote_decimal`·상수) |
| `_held()` | 기존 `preview()` 안의 dict comprehension을 그대로 옮긴 것(diff에서 본문 동일). `preview()` 동작 변화 없음 → 기존 `tests/test_imports.py` 22함수 변경 없이 통과 |

#### 재현(절대 경로, bash)
| 명령 | 결과 | 보고 |
|---|---|---|
| backend\ `py -3.11 -m uv run pytest 2>&1 \| tail -1` | **629 passed** in 126.97s | 629 일치(직전 614 → +15 = `test_imports_manual.py` 함수 11 + parametrize 4) |
| `pytest tests/test_imports.py tests/test_imports_manual.py` | 59 passed | — |
| `ruff check .` / `ruff format --check .` | All checks passed / 136 files already formatted | 일치 |
| frontend\ `unset VIRTUAL_ENV && npm run build && npm run lint && npm test` | build exit 0(262ms) · oxlint 출력 없음(0건) · **29 files / 173 tests** | 일치(직전 검증 28/167 → +1 파일/+6 = `Import.test.tsx` 6건) |
| `py -3.11 -m uv run python -m app.export_openapi <scratch>/openapi.json` → `diff` with `frontend/src/api/openapi.json` | 바이트 동일 | — |
| `npx --yes openapi-typescript@7 src/api/openapi.json -o <scratch>/schema.d.ts` → `diff` | 바이트 동일(openapi-typescript 7.13.0) | — |
| `git ls-files --eol`(수정 11) / CR 개수(신규 2) | 모두 `w/lf` / CR 0 | — |
| 색 | `Import.tsx`에 `#rrggbb`·`text-red-*` 류 없음. 토큰 클래스만 | — |

#### 반박 시도(스크래치 `<scratch>\verify-manual\probe.py`·`probe2.py`: 메모리 DB·`FakeProvider`·`AM_DATABASE_URL=sqlite://`, 실제 DB·`.env` 미접촉)
| 공격 | 결과 |
|---|---|
| `_manual_row`가 `_row`를 그대로 타는가 | 입력 → `ExtractedHolding`(이름 = `CRYPTO_ASSETS` 또는 티커, `ticker_shown=True`, `confidence="high"`, `cost_krw` 등 None) → `self._row(holding, held, fx_today)` 한 번 호출. 뒤처리는 `origin`·`currency`(사용자 선택)·채운 행의 `price_estimated/message`·채우기 실패 행의 `message`만. 티커 확인(`_resolve`)·보유 차이(`diff`/`delta_*`)·단가 의심(`_misread_price`/`_price_doubt`) 복제 없음. 같은 KRW 가격을 스크린샷 경로(`ExtractedHolding.avg_price_krw`)로 넣었을 때 `status`·`warning` 문자열이 바이트 단위로 같음(probe2) |
| 단가 비움: 시세 심볼 | 주식 → `symbol`, USD 코인 → `XXX-USD`, KRW 코인 → `UPBIT_MARKETS[symbol]`(`KRW-XXX`). probe: AAPL 295.364551→**295.36**, XRP-USD 3.159777→**3.1598**, KRW-BTC 298,616,346.0487→**298616346**. `_quote_decimal`(KRW: <1000이면 2자리 아니면 1원 / USD: <10이면 4자리 아니면 2자리) = `TransactionForm.tsx:87`의 `places` 규칙과 같음 |
| 시세 실패가 요청을 깨는가 | `provider.unknown={ETH-USD, ZZZZ}` + MSFT 3행 → 200. ETH-USD·ZZZZ는 `unknown`("… 시세를 찾을 수 없습니다"), MSFT는 `ok`+채움. KRW 코인에서 업비트만 실패(`KRW-SOL`)하면 `invalid`+"KRW-SOL 현재가를 받지 못해…"(기존 테스트). `_manual_row`는 `SymbolNotFoundError`만 잡고 `DomainError`는 주식+KRW에서만 던진다(의도된 422). `MarketDataError`(네트워크)는 전체 요청 502 — 스크린샷 `_resolve`와 같은 기존 동작 |
| `price_estimated` 행 기본 선택 | 응답 `status=ok, warning=None, diff=new, price_estimated=True, message="평균단가를 입력하지 않아 현재가로 채웠어요. 수익률이 0%에서 시작하니 …"`. 프론트 `toEditable.include = ok && (new 또는 delta) && !warning` → 선택됨(vitest `toBeChecked`). 메시지는 단가 셀 아래에 보이고 `RowStatus`는 `!price_estimated`일 때만 message를 또 보여 중복 없음 |
| 입력 검증(422) | 소수 9자리 수량·단가(`decimal_max_places`), 수량 0·음수, 빈 심볼, 21자 심볼, 101행, 통화 JPY, 자산 bond, 주식+KRW("주식은 달러(USD)로만 기록합니다") 모두 422. `"1e1"`은 200·수량 10(`f"{…:f}"`가 지수 제거), 공백만인 심볼은 200·행 `unknown`("티커를 알 수 없습니다") — 요청 단위 실패 아님 |
| 통화 되돌림 | `_row`가 추론한 통화와 `r.currency`가 다를 수 있는 경우는 코인+USD+단가 없음+시세 실패뿐이고 그때 `status`는 이미 `unknown`이라 `held_currency` 비교·delta(둘 다 `ok`/같은 통화 조건)가 잘못된 통화로 계산되지 않음 |
| 추출기 독립성 | 테스트 override 없이 실제 `get_extractor`: `AM_IMPORT_EXTRACTOR=claude`+키 없음 → `/imports/status` `configured=false`, `/imports/manual` **200**, `/imports/commit` **200**(created 1). 기본값 `ollama`도 같음. `RefusingExtractor`를 override로 두고 `/imports/screenshot`에 PNG를 올리면 **500**(AssertionError 전파) → 테스트의 거부 추출기가 실제로 호출 시 실패함을 확인. 같은 상태에서 `/imports/manual`은 200 |
| 프론트 전송값 | vitest가 `{asset_type, symbol:'AAPL', quantity:'10', avg_price:null, currency:'USD'}`·`avg_price:'300.5'` 문자열 단언. `merge`는 `source.symbol` 키로 교체, 키 없으면(미해결) 뒤에 붙임(코드 검토). `recognize`는 `origin==='manual'` 행만 남기고 스크린샷 행을 merge(코드 검토, 자동 테스트 없음). `configured=false` → 왼쪽 카드만 `SetupNeeded`, 오른쪽 직접 입력 동작(vitest) |
| 네비 라벨 | `App.tsx` `NavLabel`은 시뮬레이션에 계속 쓰임. "스크린샷 가져오기" 문자열은 `BulkDelete.tsx:8`의 `IMPORT_NOTE` 상수만 남음(ISSUE-047) |
| 정직성·문구 | HEAD의 `Import.tsx`에도 투자 조언 고지는 없었음(예측·시뮬레이션 화면이 아님) → 유지할 것이 없고 사라진 것도 없음. 새 문구에 통계 용어 없음. `FILLED_WITH_MARKET_PRICE`가 "현재가로 채움·수익률 0% 시작·거래 내역에서 고치세요" 뜻을 그대로 담음 |
| 합성 데이터 | 테스트·프로브 값은 AAPL 10@150, MSFT 2, BTC 0.01@60000, SOL 200000원, XRP 100 등 합성값. D-032·CLAUDE.md에 실제 보유 수치 없음 |

#### 발견한 문제
- ISSUE-047(낮음, 비차단): 직접 입력 행도 거래 메모 `"스크린샷 가져오기"`로 저장되고 일괄 삭제 문구가 "스크린샷으로 가져온 거래". app-engineer가 보고에서 인지했으나 담당 외 파일(`services/transactions.py`·`BulkDelete.tsx`)이라 두었음. 리드 배정.

#### 비차단
- CLAUDE.md·D-032의 "시세를 못 받으면 그 행만 `invalid`"는 KRW 코인(야후 USD 시세는 되고 업비트만 실패)에서만 정확하다. 주식·USD 코인은 `_resolve`가 먼저 실패해 `unknown`("… 시세를 찾을 수 없습니다")이다. 행 단위 실패라는 뜻은 맞으므로 문구만 "`invalid` 또는 `unknown`"으로 고치면 된다.
- 데모 모드(`AM_MARKET_PROVIDER=fake`) 관찰: `FakeProvider`는 `KRW-BTC`와 `BTC-USD`를 2015년부터 독립 난수 경로로 만들어 `KRW-BTC ÷ (BTC-USD × KRW=X) = 0.043`(ETH 0.376, XRP 1.117, SOL 0.586). 그래서 단가를 비운 KRW BTC 행은 업비트가로 채운 뒤 `_price_doubt`(야후×환율 기준 23배)에 걸려 `warning`이 붙고 기본 미선택이 된다. 스크린샷 경로도 같은 결과(코드 경로 동일성의 증거)이고 실제 공급자에선 김치 프리미엄이 수 %라 발생하지 않는다. `test_krw_coin_is_filled_with_the_upbit_price`가 `warning is None`을 단언하지 않는 이유가 이것이다. 고치려면 `FakeProvider`의 `KRW-*`를 USD 시계열 × 환율로 파생(data-engineer 판단).
- `recognize` 뒤 직접 입력 행 유지는 코드 검토로만 확인(`usePreviewScreenshots`가 vitest에서 no-op). 자동 테스트 1건 추가하면 좋다.

#### 재현 명령
- `cd /c/Users/user/Desktop/project && git status --short && git diff --stat`
- `cd /c/Users/user/Desktop/project/backend && py -3.11 -m uv run pytest 2>&1 | tail -1; py -3.11 -m uv run ruff check .; py -3.11 -m uv run ruff format --check .`
- `cd /c/Users/user/Desktop/project/frontend && unset VIRTUAL_ENV && npm run build && npm run lint && npm test`
- `cd /c/Users/user/Desktop/project/backend && py -3.11 -m uv run python -m app.export_openapi <scratch>/openapi.json && diff <scratch>/openapi.json ../frontend/src/api/openapi.json` / frontend\ `npx --yes openapi-typescript@7 src/api/openapi.json -o <scratch>/schema.d.ts && diff <scratch>/schema.d.ts src/api/schema.d.ts`
- 프로브: backend\ `PYTHONPATH=<backend 윈도 경로> py -3.11 -m uv run python -X utf8 <scratch>\verify-manual\probe.py claude`(또는 `ollama`) / `… probe2.py`. `<scratch>` = `C:\Users\user\AppData\Local\Temp\claude\c--Users-user-Desktop-project\390c67f2-c016-4b04-a641-dbd27eed466f\scratchpad`.
