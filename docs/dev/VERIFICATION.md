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

## 포트폴리오 코치 (2026-10-27)

대상: 미커밋 작업 트리(브랜치 `agent-team`, HEAD 49d18ba). 사양은 `~/.claude/plans/cozy-noodling-volcano.md` "I. 포트폴리오 코치"와 D-033. 담당: risk-engineer(`strategy/coach.py`·`tests/test_coach.py`), app-engineer(테이블·마이그레이션·서비스·API·화면, 보고 없이 중단), evaluation-engineer(`tests/test_coach_math.py`). 검증은 세션이 두 번 끊겨 세 번에 나눠 진행했고, 이 섹션은 항목을 끝낼 때마다 덧붙였다.

**판정: 부분 통과 — 차단 1건(N-COACH-1: 단가 오류 거래가 있으면 실제 추이 낙폭·리뷰 입금 분해가 598,141% 같은 값을 사실처럼 보여 주고 닫히지 않음), 비차단 8건(N-COACH-2~9). 나머지(재현·마이그레이션·정책·독립 재계산·리밸런싱·패턴·리뷰·킬스위치·금지어·위생·무효화·화면)는 반박 실패로 통과. 상세는 아래 "최종 판정".**

→ 수정 라운드 재검증(2026-10-27, 이 섹션 끝 "#### 수정 라운드 재검증")에서 N-COACH-1(ISSUE-048)·N-COACH-2~7·9가 닫힌 것을 확인해 **통과**로 갱신. 남은 것은 N-COACH-8(관찰)·N-COACH-10(테스트 보강 권고).

#### 1. 재현(절대 경로, bash)
| 명령 | 결과 | 리드 보고와 대조 |
|---|---|---|
| backend\ `py -3.11 -m uv run pytest -o addopts="" -q` | **875 passed** in 129.19s | 875 일치 |
| `pytest -o addopts="" -q tests/test_coach.py` / `test_coach_math.py` / `test_coach_api.py` | **142** / **63** / **41** passed (0.22s / 0.14s / 7.17s) | — (리드 미보고) |
| `ruff check .` / `ruff format --check .` | All checks passed / 143 files already formatted | 일치 |
| frontend\ `unset VIRTUAL_ENV && npm test -- --run` | **33 files / 210 tests** passed | 일치 |
| `npm run lint` / `npm run build` | oxlint 0건 / built in 245ms(exit 0) | 일치 |
| `npm run gen:api` 재실행 | `openapi.json`·`schema.d.ts` sha256이 두 번 실행 사이에 동일(`4323bfe8…`, `9a1c5e08…`) → 재생성 결정적. 경로 `/api/coach/{policy,diagnosis,rebalance,patterns,review}`·`/api/rules/kill-switch/reset` 포함 | `git diff --quiet`는 HEAD 대비라 항상 1(두 파일이 작업 트리에서 이미 수정됨) — 해시 비교로 대신함 |
| `tests/test_coach_math.py`의 `xfail` | 머리말에만 언급, 실제 `xfail` 마커 0개 → 손계산과 모듈 값이 전부 일치 | — |

#### 2. 마이그레이션(데모 DB `backend/demo.db`, `AM_DATABASE_URL=sqlite:///demo.db`)
| 확인 | 결과 |
|---|---|
| `alembic heads` | `8ed46201b220 (head)` 하나. 파일 `down_revision = '3af66f72d79b'` |
| `alembic upgrade head` | e67d73f03bf8 → 9f363af5cd85 → e8db9ec1f27b → 6de1dd6fc3d6 → 3af66f72d79b → **8ed46201b220**(데모 DB가 5단계 뒤에 있었음. 중간의 "invalidate symbol syncs" 마이그레이션으로 `symbol_syncs`가 비워져 첫 코치 호출이 봉을 다시 받음) |
| `alembic check` | "No new upgrade operations detected." |
| `policy_settings` | `pragma table_info`: `id INTEGER PK`, `policy_json JSON NOT NULL`, `cash_json JSON NOT NULL`, `updated_at DATETIME NOT NULL` = `PolicySettingsRow`와 일치. 행 0개(정책 미저장) |
| 마이그레이션 형식 | `op.create_table(...)` + `op.f('pk_policy_settings')` 명명 규칙. 새 테이블 생성이라 `batch_alter_table`은 해당 없음(`render_as_batch`는 ALTER에만 적용) |
| `seed.load` | 데모 DB에 거래 **21건**(14종목: 데모 16건 + 2026-10-19 직접 입력 검증 5건, 코인 4종은 KRW)이 이미 있어 `seed.load`가 "already exist"로 거부 → `--reset` 없이 기존 데모 데이터로 진행 |

#### 8. 금지 사항 grep
| 확인 | 결과 |
|---|---|
| `추천|사세요|파세요|오를|예상 수익` in `strategy/coach.py`·`services/coach.py`·`schemas/coach.py`·`api/coach.py`·`lib/coach.ts`·`Coach.tsx`·`CoachCard.tsx` | 5건, 전부 고지문·주석: `coach.py:18`(모듈 docstring "…을 피한다"), `coach.ts:5-6`(주석), `coach.ts:25` `COACH_INTRO_KO` "예측·종목 추천·투자 조언이 아니며"(고지), `coach.ts:415`(주석 "Never 사세요/파세요"). 사용자에게 보이는 문장 중 금지어는 고지문 1건뿐 |
| `execute(`·`Broker`·`.trip(`·`KillSwitch.trip` in `strategy/coach.py`·`services/coach.py` | 0건. `services/coach.py`는 `KillSwitch(self.db).state()`만 읽음 |
| `git diff backend/app/config.py` | `coach_max_crypto_weight_pct`(30, gt 0 lt 100)·`coach_max_total_risk_pct`(8) 추가만. `live_trading` 변경 0 |
| `FakeProvider`·합성 대체 | `services/coach.py`·`strategy/coach.py`·`api/coach.py`에 0건. 봉 없는 종목은 `_bars` → `None`+이유 → `excluded`/caveat로 보고(대체 없음) |
| `STRATEGY_CONFIGS_TRIED`·STRATEGIES.md | 코드 변경 0. 작업 트리 diff에서는 DECISIONS.md·CLAUDE.md 문장("올리지 않는다")에만 등장 |

#### 10. 무효화(`hooks.ts` diff)
`useLedgerMutation`(거래 생성·수정·삭제 공통) `onSuccess`에 `['coach']` 추가, `useUpdateRuleSettings`가 `['rules']`+`['coach']`, `useResetKillSwitch`가 `['rules']`+`['coach']` 무효화. 코치 훅 키는 모두 `['coach', …]`(staleTime 5분, `retry: false`, 리뷰는 `keepPreviousData`). 통과.

#### 11. 공개 저장소 위생
`git status --porcelain`·`git ls-files`에 `*.db`·`.env`·`artifacts/` 없음. 새 테스트 입력은 합성(`test_coach_math.py` AAA/BBB/XXX, `test_coach_api.py` AAPL 10@100·MSFT 5@200·BTC 0.01@8천만원 등 FakeProvider 값). 이 섹션의 수치도 데모 DB(`seed.load`)와 합성값만 쓴다. 통과.

#### 7. 킬스위치 리셋(코드 읽기 + 테스트)
`api/rules.py`: `POST /rules/kill-switch/reset`, 본문 `KillSwitchResetIn | None`(`detail: str = Field("", max_length=200)`만, actor 필드 없음) → `RuleService.reset_kill_switch(detail)` → 켜져 있을 때만 `KillSwitch.reset(actor="user", detail=detail)`, 아니면 쓰기 없이 현재 상태 반환 → `kill_switch_payload`. `test_coach_api.py::test_reset_turns_the_switch_off_and_records_the_user_as_actor`가 본문의 `"actor": "system"`을 무시하고 이벤트 `actor == "user"`를 단언, `…_when_not_tripped_answers_200_without_writing`이 이벤트 0건·본문 없음 200을 단언(둘 다 41건 통과에 포함). 통과.

#### 9. 화면 정직성(코드 읽기)
| 확인 | 결과 |
|---|---|
| `text-gain`/`text-loss`/`PnL`/▲▼ 위치 | `lib/coach.ts`·`CoachCard.tsx`·`CorrelationHeatmap.tsx`: 0건. `Coach.tsx`: `PnL` 5곳만 — 576(리밸런싱 표 "매도 시 실현손익" `realized_pnl_krw_if_sold`), 733(리뷰 시장 손익), 734(리뷰 실현손익), 735(리뷰 배당), 746(리뷰 벤치마크 초과). 변동성·낙폭·베타·상관·리밸런싱 금액(`rebalanceActionPhrase` 순수 문자열)·차이(`formatPct` 부호만)에는 손익 색·▲▼ 없음. 낙폭은 `−` 기호 문자열 |
| 계획과 다른 점 | 계획("월간 리뷰의 실현 숫자에만 허용")과 달리 리밸런싱 표의 **가상** 실현손익(`realized_pnl_krw_if_sold`, 576행)에도 `PnL`을 썼다. 리드가 갱신한 CLAUDE.md 코치 절은 이를 명시적으로 허용("…매도 시 실현손익 참고값에만 `PnL`")하므로 차단하지 않음. 다만 "팔았다면"이라는 가정값에 손익 색이 붙는 유일한 자리라 비차단 권고로 남김(N-COACH-3) |
| 색 | 7개 파일에 `#hex`·`rgb(`·`hsl(` 0건. `CorrelationHeatmap`은 `color-mix(in oklab, var(--series-2|--series-1) N%, var(--fill))`, 대각선 `var(--fill)`(`index.css`에 라이트·다크 토큰 존재) |
| 헤더 고정 문장 | `COACH_INTRO_KO` = 계획 문장과 글자 단위 일치. 바닥 `COACH_FOOTER_KO` "투자 조언이 아닙니다. 수수료·세금 미포함."(`Coach.tsx:105`). 홈 카드 "내가 정한 정책 기준의 점검이에요. 투자 조언이 아닙니다." |
| 킬스위치 해제 버튼 | `StatusStrip`: `kill.tripped &&`일 때만 "해제" → 인라인 확인("해제 확인"/"취소") → `useResetKillSwitch().mutate(undefined)`(본문 `{detail: ''}`). 규칙 점검이 로딩/실패면 스트립 자체 숨김. vitest `has no reset button while the switch is off`·`asks twice inline…` |
| 현금 미입력 안내 | `CASH_NOTE_KO` "현금은 이 앱이 알 수 없어 직접 적습니다…"(폼), 진단 타일 "현금 미입력 · 투자금만 …", 체크리스트 "현금을 적지 않아 확인할 수 없어요", 리밸런싱 notes에 서버 `NO_CASH_NOTE_KO` |
| 규칙 페이지 링크 | `Coach.tsx:268-274` "종목별 목표 비중은 [규칙 페이지에서] 정합니다. 코치는 그 값을 그대로 읽고 새 종목을 끼워 넣지 않습니다." |
| 과거 추정값 단서 | `swingPhrase` "…지난 1년 기준", `drawdownPhrase` "지난 3년을 지났다면", 베타 "지난 1년", 히트맵 캡션 "과거 값이며 미래를 보장하지 않습니다", 진단 caveats 첫 줄이 서버 `PAST_CAVEAT_KO` "과거 데이터로 추정한 값이며, 과거는 미래를 보장하지 않습니다." |
| 홈 `CoachCard` | `Dashboard.tsx`에서 `<RulesBanner />` 바로 아래. `coachSummary(undefined)` → 렌더 없음(로딩·오류). 정책 없음 → "정책을 아직 정하지 않았어요 →". 단, `coachSummary`는 `policy_set` 검사를 `empty` 검사보다 먼저 하므로 **보유가 없고 정책도 없으면** 카드가 나온다(CLAUDE.md "보유 없음이면 숨김"과 미세하게 다름, N-COACH-4) |

#### 3. 독립 재계산(데모 DB, 실제 공급자, 스크래치 `coach_demo.py` → `coach_recompute.py`)
호출은 `TestClient(app, base_url="http://localhost")`(conftest와 같음, `AM_DATABASE_URL=sqlite:///demo.db`, `market_provider=yfinance`, `live_trading=False` 확인 후 진행). 데모 보유 14종목(주식 10 USD + 코인 4 KRW). 재계산은 `price_bars`를 sqlite3+pandas로 직접 읽어(주식·USD = `adj_close`, `KRW-*`·`KRW=X` = `close`, 응답의 3y 창 `end`=2026-10-26까지) 주식 거래일 격자(772일)에 코인·환율을 전일 채움 → 원화 수익률 → 창 자름(`index ≥ today−365/1095`) → 포함 종목(유한 수익률 ≥120) → `dropna` → `σ(ddof=1)`, Ledoit-Wolf 상관(sklearn `LedoitWolf`를 표준화 수익률에 직접 적용; `app.forecast.aggregate.correlation`과 max|Δ| **0.0**) → `√(wᵀΣw)·√252` → 고정 비중 지수 낙폭·고점/저점.

| 항목 | 응답 | 재계산 | 차이 |
|---|---|---|---|
| 비중·`invested_weight_pct`(14종목), `stock/crypto/usd/cash_pct`, HHI·`effective_n`·top1·top3 | — | — | 전부 **0.0** |
| 1y: rows 251, 2025-10-27~2026-10-26, grid stock, ppy 252, coverage 100, method ledoit_wolf | `annual_vol_pct` 25.6954, `swing` 14,949,205원, `max_dd` 17.3227% (고점 2026-01-16 → 저점 2026-03-30) | 동일 | **0.0**(허용 1e-6 / 1e-9) |
| 3y: rows 750, 2023-10-30~2026-10-26 | `annual_vol_pct` 26.6617, `swing` 15,511,387원, `max_dd` 27.9554% (2025-01-21 → 2025-04-08, `peak_at_window_start=False`) | 동일 | **0.0** |
| 참고 | 표본(비축소) 상관으로는 1y 26.19% / 3y 26.99% → LW 축소가 약 0.5%p 낮춤(정상) | | |
| 상관표 14×14 | method ledoit_wolf, rows 750, 대각 1·대칭 | max|Δ| 0.0 | 통과 |
| 베타 13종목(주식 10 → SPY 256일, KRW 코인 3 → KRW-BTC 374일; BTC는 자기 벤치마크라 행 없음) | 예 VOO 0.9953/r² 0.9991, MU 3.3637, ETH-USD 1.2259 | 전부 동일 | **0.0** |
| 현금 저장 뒤(2천만원+$1,000, 환율 1323.18) | `equity` 79,501,708원, `cash_pct` 26.82, 1y vol 18.8036 / 3y 19.5108, 3y dd 21.1300 | 동일 | 0.0 |
| 필요 수익률(목표 3억·10년·월 50만) | 9.919252515592 | brentq 9.919252515540 | 5e-11(상대) |
| `risk.actual`(TWR) | `twr_max_drawdown_pct` **598,141.18**, `current` 584,636.71, 일일 −3% 초과 5, 낙폭 초과 1, points 709, since 2024-11-18 | 공식대로 재계산하면 동일(차이 0.0) | 공식 일치, **값은 비정상** → N-COACH-1 |
| 제외·`coverage`·`usable` 규칙 | 데모는 전 종목 이력이 길어 제외 0 → 규칙은 `test_coach_math.py::TestShortHistoryAndCoverage`(제외·재정규화, 70% → usable False, <120행 → identity) 3건과 `test_coach.py` 4건으로 확인 | | |

전체 123(현금 없음)+126(현금 있음) 대조 중 FAIL 0.

#### 4. 리밸런싱 계약(스크래치 `coach_contracts.py`·`coach_demo2.py`·`coach_contracts2.py`, 데모 DB; 끝에 정책 행 삭제·규칙 목표 복원)
| 확인 | 결과 |
|---|---|
| 기본(허용 오차 5, 현금 없음) | `cash_known=False`, `class_targets.cash=None`, 주식/코인 80/20으로 재정규화, notes에 `NO_CASH_NOTE_KO`·"비중 상한으로 2.3%p가 현금으로 남습니다"·수수료 문구. 모든 drift가 5%p 안이라 **주문 0건**(`after`=현재) — 허용 오차 규칙 확인 |
| 허용 오차 0.5, 현금 없음 | 주문 발생. 매도(VOO·BTC·ETH·XRP) → 매수 순서, 매수 합 1,258,550 ≤ 매도 대금 3,311,346, `after.cash_krw` = 남은 대금 2,052,795(복제 계산과 일치), 어떤 매수도 현금 보유를 넘지 않음 |
| 허용 오차 0.5, 현금 2,132만원, 60/20/20 | 매수 5건 전부 accepted, 현금 범위 안. `after` 비중·현금 = 주문을 내 손으로 적용한 장부와 max|Δ| **0.0** |
| 종목 목표(규칙 페이지 `targets_json`) VOO 40·AAPL 30·MSFT 40, 자산군 주식 60 | 합 110 > 60 → `source=scaled`(VOO 21.8→**cap 20 capped**, AAPL 16.36, MSFT 21.8→20 capped), note "주식 종목 목표의 합 110%가 자산군 목표 60%를 넘어 비례로 줄였습니다"·"비중 상한으로 3.6%p가 현금으로 남습니다", 진단 `violations`에 `targets_exceed_class`(info, value 110, limit 60). 목표 없는 주식 7종은 target 0 → 전량 매도(N-COACH-9). AAPL·MSFT 매수는 `max_order_fraction`(5% = 3,973,055원)으로 `clipped`, label "1회 주문 상한" |
| 코인 자산군 목표 0 | 코인 4종 `source=class_zero`, 각각 **현재 평가액 전액 매도**(8,536,800 / 2,598,000 / 2,474,400 / 1,072,000 = 같은 세션 `holdings` 평가액) |
| `realized_pnl_krw_if_sold` | 매도 행마다 `allowed × (1 − cost_basis_krw/market_value_krw)`와 일치(예 NVDA +939,697, TSLA −750,125; 단가 오류 행 GOOG −1,019억 등 N-COACH-1과 같은 뿌리). 매수 행은 None. 부호 = 장부 평가손익 부호 |
| 새 종목 | 모든 케이스에서 `targets`·`orders` 심볼 집합 ⊆ 보유 집합(`targets` = 보유 전체) |
| 코인 합산 상한 위치 | `construct_targets` → `cap_class_weights({"crypto": policy.max_crypto_weight_pct/100})` → `risk.cap_weights(policy.limits(base))`. `RiskLimits`에 코인 필드 없음(diff 확인), `Policy.limits`는 종목 상한을 `min(base, policy)`로 좁히기만 함 |
| 기준선 테스트 | `test_coach_math.py::TestRebalanceBand`(4pt 안 → 0건, 정확히 5pt → 0건, 6pt → 매도 60,000 뒤 매수, 매도 대금 초과 매수 → `cash`로 clipped, 매도 없고 현금 0 → `cash` rejected, 5% 주문 상한), `test_coach_api.py::test_rebalance_sells_first_and_notes_the_missing_cash` 통과. 데모에서는 매도 대금이 매수 수요보다 커 `cash` 사유가 실제로 찍히지 않아 이 두 테스트에 의존 |
| 한 번 더 주의 | 첫 forced 실행에서 realized·after가 어긋났으나 원인은 **내 스냅샷**(`holdings`를 첫 실행 때 받아 두고 두 번째 실행에서 비교, 60초 quote 캐시 만료로 평가액이 수백~수만 원 이동). 같은 세션 스냅샷으로 재실행 → 123/123 통과 |

#### 5. 정책·현금
| 확인 | 결과 |
|---|---|
| `GET /api/coach/policy` 기본값(행 없음) | `max_position_weight_pct` 20 (= `risk_max_position_weight` 0.20×100), `drawdown_tolerance_pct` 20, `target_stock/crypto/cash` 80/20/0 (= `strategy_budget_*`, 현금 나머지), `max_crypto_weight_pct` 30, `max_total_risk_pct` 8, `rebalance_band_pt` 5 (= `rules_target_weight_gap_pt`), goal None, `policy_set=false`, `updated_at=null`, `cash=null`. `from_config`는 코인 예산을 코인 상한으로 clamp(테스트 `test_from_config_clamps_crypto_budget_to_the_crypto_cap`) |
| PUT 문자열 Decimal | `test_put_parses_strings_stores_them_exactly…`: 행에 `"12.5"`·`"10000000"` 문자열 저장, GET 왕복 동일 |
| 422 케이스(데모 실행) | 합 110 → 422 "자산군 목표 비중(주식·코인·현금)의 합이 100이어야 합니다 (지금 110%)" `code=invalid_policy`; 코인 50 > 상한 30 → 422 "코인 목표 비중(50%)이 코인 합산 상한(30%)보다 큽니다"; `"NaN"` → 422(pydantic `finite_number`, 서비스 `_dec`도 non-finite 거부); `goal_date "2027-13-40"` → 422(pydantic date); 현금 −1 → 422(`ge=0`); 현금 날짜 누락 → 422(`missing`). 여섯 번 뒤 `policy_set` 여전히 False(저장 없음). 테스트 9+4 케이스 추가 통과 |
| 허용 낙폭 25 | 200 저장, `warnings` ["허용 낙폭 25%는 프로젝트 전략 한도(20%)보다 느슨합니다"], `policy.drawdown_tolerance_pct` 25 |
| `cash_stale` | 기준일 37일 전 → `cash_stale=true` + "현금 기준일이 37일 지났습니다…"; 테스트는 31일 true / 30일 false 경계 확인. 진단 `violations`에 `cash_stale`(info)·현금 없으면 `cash_missing`(info) |
| 종목 상한이 리스크 한도보다 넓을 때 | `Policy.limits`가 좁히기만 하므로 정책 30%를 적어도 20%가 적용되고 `warnings`에 "종목 상한 30%는 모의투자 리스크 한도(20%)보다 느슨합니다…"(코드 `_notes`). 계획대로 |

#### 6. 패턴·리뷰
| 확인 | 결과 |
|---|---|
| 경계 규칙(엔진 = 테스트 = 서비스 문구) | 추격 매수 `run_up > 15 + EPS`(정확히 15%는 아님, 봉 < 21개는 `skipped`) ↔ "15% 넘게"; 물타기 `price ≤ avg×(1−cut) + EPS`(선 위 포함) ↔ `test_84_and_85_are_at_or_below…86_is_not`; 손절선 아래 보유 연속 `≥ 5`봉; 과매매 `total ≥ 6`이고 `> 2×직전 ≤12개월 평균`(첫 달 제외); 손실 매도 뒤 재매수 `gap ≤ 10`(10일 포함, 11일 제외). `test_coach_math.py` 5개 클래스·`test_coach.py` 6개 함수와 일치 |
| 데모 재계산(스크래치) | 최근 1년 거래 12건: 추격 0·물타기 0·재매수 0(각각 내 재계산과 집합 동일, `trades_without_bars` 0), 월별 24개월 집계(빈 달 0 포함) 동일, 과매매 0. `rule_lag` 8종목 중 TSLA 75봉은 정확히 일치; 나머지 7종목은 창 전체가 손절선 아래여서 `days`가 **봉을 받은 범위의 길이**(API 282 = 45일 여유, 내 60일 여유 292; 코인은 당일 미확정 봉 ±1) → N-COACH-6 |
| 리뷰 (start, end] | 2026-10: `start` 2026-09-30, `end` 2026-10-27(오늘), 2026-09: 08-31~09-30. `change = contributions + market_pnl` 항등식, `change = end − start`, 시작·끝 값 = `/api/portfolio/history`의 해당 날짜 값과 일치 |
| 입금 재계산 | 거래×환율(`KRW=X` 거래일 이전 마지막 종가, 수수료 포함) 합: 2026-10 **339,776,877,723원**(API와 동일 — 단가 오류 5건, N-COACH-1), 2026-09 0, 2026-04 −2,682,296(매도) |
| 실현손익 | 매도가 있는 달을 장부 규칙(매수일 환율 원가 비례 방출, 매도일 환율 대금)으로 재계산: 2026-04 762,628.06 / 2026-06 692,217.23 / 2026-07 −847,279.33원 — API와 소수 둘째 자리까지 일치. 배당 0(데모에 confirmed 배당 없음) |
| 벤치마크 | `[SPY, BTC-USD]` 순서, `excess = 내 change − 벤치 change` 항등(예 2026-09 SPY −1,438,232 → 초과 +2,162,433) |
| `months_available` | 첫 거래 2024-11 → 2026-10, 24개, 최신 먼저. 미래 달·`2026-13`·`abc` → 422(테스트) |
| `violations_now` | 리뷰는 봉 없이 비중·노출 검사만(3건) ↔ 진단 warn 5건 → N-COACH-5 |
| `flagged_trades` | `patterns()`(최근 1년) 결과를 달로 걸러 쓰므로 1년보다 오래된 달은 항상 0 → N-COACH-2 |

#### 12. 응답 시간(데모 DB, TestClient, 봉 캐시 뒤)
| 엔드포인트 | 첫 호출 | 재호출 |
|---|---|---|
| `/api/coach/policy` | 0.22s | — |
| `/api/coach/diagnosis` | **11.27s**(마이그레이션으로 `symbol_syncs`가 비워져 17심볼 재동기화 포함) | 0.94s / 0.93s |
| `/api/coach/rebalance` | 0.01s | 0.01s |
| `/api/coach/patterns` | 0.18s | 0.17s |
| `/api/coach/review` | 0.79s | 0.24s(`?month=` 0.24s) |
| 참고 `/api/rules/check`(예측 포함, 코치 밖) | 25.1s | — |
코치 진단은 `RuleService(forecasts=None)`라 예측 추론 없이 1초 안(규칙 점검 단독 라우트 25s와 대비). 코치 페이지 헤더 칩·체크리스트는 `useRuleCheck()`(예측 포함 라우트)를 기다린다(N-COACH-8).

#### 발견한 문제(차단)
### [N-COACH-1] 단가 오류 거래가 있으면 실제 추이 낙폭·리뷰 입금 분해가 비정상 값을 사실처럼 보여 준다(fail-closed 아님)
- 현상: 데모 DB `/api/coach/diagnosis` `risk.actual.twr_max_drawdown_pct` **598,141.18%**, `current_drawdown_pct` 584,636.71%, `daily_loss_breaches_1y` 5, `drawdown_breaches_1y` 1, `actual_error=null`. `/api/coach/review`(2026-10) `contributions_krw` 339,776,877,723원, `market_pnl_krw` −339,765,119,414원(자산 5,818만원). 화면: "실제 추이의 낙폭" 접기에 "−598141.2%", 손실 중 체크리스트 "지금 고점 대비 −584636.7% · 허용 −20%" → 주의, 리뷰 "넣은 돈 339,776,877,723원 / + 시장 손익 −339,765,119,414원"(손익 색).
- 원인: 데모 DB 거래 id 17~21(2026-10-19, 메모 "스크린샷 가져오기" — 이전 직접 입력 검증이 남긴 행)의 `price`가 원화 총액(예 GOOG 13주 @ 5,879,484 "USD"). `benchmarks.cash_flows`가 이를 그대로 원화 입금 3,398억으로 만들고, `twr_index`의 `r_d = (V_d − V_{d−1} − f_d)/V_{d−1}`가 2026-10-19에 (59,179,366 − 45,264,772 − 339,776,877,723)/45,264,772 = **−7,506**이 되어 지수가 음수로 뒤집힌다. `twr_index`·`_actual`·`period_review`는 `1 + r_d ≤ 0`(하루에 100% 넘게 잃음)이나 음수 지수를 거부하지 않고, 단서는 "가져온 거래의 **날짜**가 다를 수 있다"만 말한다. 같은 행들은 앱의 기존 20배 규칙(`isSuspiciousCost`·`statement_import._price_doubt`)이 `단가 확인`으로 잡는 것들이다(원가/평가 3,946~68,783배).
- 근거: 스크래치 `inspect_demo.py` 출력(거래표·원가/평가 비율·2026-10-15~23 추이), `coach_recompute.py`가 같은 공식으로 598,141.18%를 재현(차이 0.0), `backend/app/strategy/coach.py` `twr_index`(829~844행, 음수 지수 무방어), `backend/app/services/coach.py` `_actual`(684~716행), `_flows`(677~682행), `IMPORTED_DATES_CAVEAT_KO`(89~92행). 메모리 노트 "user data has bad import prices" → 실제 DB에서도 재현될 가능성이 높다.
- 해결(제안, 수정은 담당자): ① risk-engineer — `twr_index`에서 어떤 날이든 `1 + r_d ≤ 0`이면 `ValueError`로 닫고(`_actual`이 `actual_error`로 날짜·사유를 보고), `period_review`도 입금이 `max(V_start, V_end)`의 수십 배면 같은 식으로 닫거나 플래그. ② app-engineer — `_flows`/`review`에서 원가/평가 20배 규칙에 걸리는 거래를 세어 caveat에 "단가 확인 거래 N건이 입금에 포함되어 실제 추이·입금 분해가 왜곡됨"을 붙이거나 그 거래를 빼고 뺐다고 적기(조용히 대체하지 않음). ③ 최소한 `drawdown`이 100%를 넘으면 숫자 대신 "계산 불가"를 보여 줄 것.
- 검증: 미해결. 재현 `cd backend && PYTHONPATH=<backend> AM_DATABASE_URL=sqlite:///demo.db py -3.11 -m uv run python -X utf8 <scratch>/coach_demo.py <scratch>/demo_out` → `demo_out/diagnosis_nocash.json` `risk.actual`. 데모 DB에서 5행을 지우면 사라지지만 코드 결함(무방어)은 그대로다. 실제 DB는 읽지 않았다.

#### 비차단
- N-COACH-2: `review.flagged_trades`는 `patterns()`의 최근 1년 창에서만 고르므로 1년보다 오래된 달은 항상 "이 달에는 없어요"가 나온다. 리뷰에 "최근 1년 거래만 점검" 단서 또는 달 기준으로 패턴 창을 잡기.
- N-COACH-3: 리밸런싱 표의 가상 실현손익(`realized_pnl_krw_if_sold`)에 `PnL`(손익 색·▲▼). 계획의 "월간 리뷰 실현 숫자에만"과 다르지만 리드가 CLAUDE.md에 허용으로 적어 두었다. 가정값임을 열 머리("매도 시 실현손익")가 말하므로 수용 가능; 색 없이 부호만으로 바꾸면 계획과 완전히 맞는다.
- N-COACH-4: `coachSummary`가 `policy_set` 검사를 `empty` 검사보다 먼저 하여 보유 0·정책 없음이면 홈 카드가 "정책을 아직 정하지 않았어요 →"를 보여 준다(CLAUDE.md "보유 없음이면 숨김"). 의도된 유도라면 문서를, 아니면 순서를 고치면 된다.
- N-COACH-5: 리뷰 머리 "지금 정책 위반 N건"(`_violations_now`, 비중·노출만, 데모 3건)과 진단 머리 "정책 위반 N건"(warn 전체, 데모 5건)이 같은 말로 다른 수를 낸다. 리뷰 쪽 문구를 "비중 기준 위반"으로 바꾸거나 진단 수를 재사용.
- N-COACH-6: `rule_lag`의 `since`·`days`는 봉을 받은 범위(`window_start − 45일`)에 갇힌다. 창 전체가 손절선 아래면 `since`가 실제 교차일이 아니라 조회 시작일이고 "N봉째"가 조회 길이다(데모 7종목 282봉). `since_capped`류 플래그나 "최소 N봉" 표기 권고.
- N-COACH-7: `violations()`의 `drawdown_over_tolerance` detail이 창 이름을 그대로 써 "지난 **3y**을 지났다면"으로 나온다(`risk3y.name`). 한국어 라벨(`3년`) 매핑 필요(엔진 또는 서비스).
- N-COACH-8(관찰): 코치 헤더 칩·체크리스트는 `useRuleCheck()`(예측 추론 포함, 데모 25s)를 기다린다. 코치 자체는 1초 안이라 코치 결함은 아니지만 첫 방문 체감에 영향.
- N-COACH-9: 종목 목표 합 ≥ 자산군 목표면 목표 없는 같은 자산군 종목은 target 0(`source=remainder`)이 되어 전량 매도 제안이 된다(데모: 주식 7종). 계획 규칙의 논리적 결과이지만 notes가 "비례로 줄였습니다"만 말하고 "목표 없는 종목은 0%"를 말하지 않으며, 0%짜리 `source=remainder`는 오해를 부른다("class_full" 같은 별도 source나 note 권고).
- 참고: 데모 DB 마이그레이션 중 `9f363af5cd85`가 `symbol_syncs`를 비워 첫 진단이 11s 걸렸다(예상된 동작). 검증 뒤 데모 DB의 `policy_settings` 행은 삭제하고 `rule_settings.targets`는 `{}`로 되돌렸다(마이그레이션은 유지).

#### 계획과 다르게 구현된 점(허용 여부)
| 항목 | 계획 | 구현 | 판단 |
|---|---|---|---|
| 스키마 필드 | `PolicyOut{policy, cash, defaults, warnings, updated_at, cash_stale}` 등 | `policy_set`, `DiagnosisOut.goal_years`·`weights[].cap_pct`·`risk.actual_error`·`actual.points/drawdown_breaches_1y`·`correlation.excluded`·`RiskWindowOut.peak_at_window_start`, `RebalanceOut.empty/headline_ko/price_krw`, `PatternsOut.empty/months`, `ReviewOut.empty/start_point/end_point` 추가 | 추가만 있고 누락 없음. 허용 |
| `from_config` | 자산군 목표 = 예산×100 | 코인 목표를 코인 상한으로 clamp(아니면 `Policy`가 ValueError) | 합리적. 허용 |
| `RuleService.check_all`이 현금 `Book` 사용 | "선택 WP" | 미구현(`check_all()` 인자 없음) | 선택 항목. 허용(TODO로 남길 것) |
| 과매매 입력 | "최근 1년 거래" | 월별 집계·과매매는 전체 거래(기준 12개월이 필요) | 합리적. 허용 |
| 킬스위치 해제 확인 | "확인 뒤" | `window.confirm` 대신 인라인 2단계 버튼 | 허용 |
| 리밸런싱 가상 실현손익 색 | 리뷰 실현 숫자에만 `PnL` | 리밸런싱 표에도 `PnL`(N-COACH-3) | CLAUDE.md가 허용으로 갱신됨. 허용(권고만) |
| 홈 카드 숨김 조건 | 로딩·오류 숨김, 정책 없음 문구 | 보유 0+정책 없음에도 문구(N-COACH-4) | 경미. 허용 |
| 브라우저 확인(390px·다크·킬스위치 trip) | 계획의 verifier 항목 | **수행하지 못함**(이 세션은 코드·API 검증만; vitest 15건이 섹션·버튼 조건·고지를 대신 확인) | 리드가 수동 확인 또는 다음 라운드 |

#### 최종 판정
**부분 통과.** 재현(875/142·63·41/210)·마이그레이션·정책 검증·독립 재계산(변동성·낙폭·상관·베타·필요 수익률 차이 0)·리밸런싱 계약(246 대조 통과)·패턴·리뷰(실현손익까지 일치)·킬스위치 리셋·금지어·위생·무효화·화면 정직성은 반박에 실패해 통과. **N-COACH-1만 차단**: 단가 오류 거래가 있을 때 `risk.actual`과 리뷰 입금 분해가 598,141% 같은 불가능한 값을 사실처럼 보여 주고 닫히지 않는다. 실제 사용자 데이터에 단가 오류 가져오기 행이 있다고 기록돼 있어 해결(또는 해당 표시 숨김) 전 커밋은 권하지 않는다. 그 외 N-COACH-2~9는 비차단.

#### 재현 명령
- backend\ `py -3.11 -m uv run pytest -o addopts="" -q` / `… tests/test_coach.py tests/test_coach_math.py tests/test_coach_api.py` / `ruff check .` / `ruff format --check .`
- frontend\ `unset VIRTUAL_ENV && npm test -- --run && npm run lint && npm run build && sha256sum src/api/openapi.json src/api/schema.d.ts && npm run gen:api && sha256sum src/api/openapi.json src/api/schema.d.ts`
- backend\ `py -3.11 -m uv run alembic heads; AM_DATABASE_URL=sqlite:///demo.db py -3.11 -m uv run alembic upgrade head; … alembic check`
- 데모 API·재계산(`<scratch>` = `C:\Users\user\AppData\Local\Temp\claude\c--Users-user-Desktop-project\390c67f2-c016-4b04-a641-dbd27eed466f\scratchpad`): backend\ `PYTHONPATH=<backend> AM_DATABASE_URL=sqlite:///demo.db py -3.11 -m uv run python -X utf8 <scratch>/coach_demo.py <scratch>/demo_out` → `… coach_recompute.py demo.db <scratch>/demo_out diagnosis_nocash.json`(및 `diagnosis_cash.json`) → `… coach_contracts.py demo.db <scratch>/demo_out` → `… coach_demo2.py <scratch>/demo_out && … coach_contracts2.py <scratch>/demo_out` → `… coach_review_realized.py <scratch>/demo_out` → `… inspect_demo.py demo.db <scratch>/demo_out`
- 서버는 띄우지 않았다(TestClient). 실제 DB(`asset_manager.db`)·`.env`는 읽지 않았다.

#### 리드 브라우저 확인 (2026-10-27, Chrome, verifier가 하지 못한 항목)
verifier는 세션이 끊겨 브라우저 확인을 수행하지 못해 리드가 대신했다. 실제 DB 수치는 적지 않는다.

| 확인 | 결과 |
|---|---|
| 실제 DB 마이그레이션 | `alembic upgrade head` 3af66f72d79b → 8ed46201b220, `alembic check` "No new upgrade operations". `.\scripts\dev-backend.ps1`로 8001 재시작 뒤 `GET /api/coach/policy` 200 |
| `/coach` 데스크톱 라이트(실제 DB, 정책 없음) | 헤더 고정 문장 → 킬스위치 꺼짐·실매매 꺼짐 칩 → "아직 정책을 저장하지 않아 서버 설정의 기본값" 안내 → 정책 폼(목표·한도·자산군 목표·현금 잔고, 저장/기본값) → 진단 StatTile 6개 → 위반 목록 → 접기 3개(상관 히트맵 6×6 전 셀 숫자·범례 "축소 추정(Ledoit-Wolf) · 겹치는 N일 · 과거 값이며 미래를 보장하지 않습니다", 베타 문장+단서, 실제 추이 낙폭 3행) → 체크리스트(사기 전 5항목·손실 중 4항목) → 리밸런싱 표(상한 적용 배지, "줄이기 X원 · 약 N주", 막힌 이유, 매도 시 실현손익, "모두 반영하면", 메모 4줄) → 습관 점검(패턴 5종 칩) → 월간 리뷰(달 선택, 변화 분해, 벤치마크 대비, 플래그 거래) → 바닥 고지. 콘솔 오류 0 |
| 다크 | `data-theme=dark`에서 바탕 `rgb(23,23,28)`, 히트맵 셀·표·칩 모두 토큰 색으로 바뀜 |
| 390px | 창 크기 조절 API가 최대화된 창에 먹지 않아 같은 페이지를 390px iframe으로 확인: `scrollWidth` 375 ≤ 387(가로 넘침 없음), 리밸런싱 표만 래퍼 `overflow-x:auto` 안에서 가로 스크롤(표 380px), StatTile 1열, 네비 줄바꿈 |
| 홈 `CoachCard` | 규칙 배너 바로 다음 자식으로 "포트폴리오 코치 정책을 아직 정하지 않았어요 →" + "내가 정한 정책 기준의 점검이에요. 투자 조언이 아닙니다." |
| 킬스위치 해제(데모 DB, 8002 백엔드 + 5174 프론트) | 스크래치 스크립트로 `KillSwitch.trip("manual", …, actor="user")` → `/coach` 헤더 "킬스위치 켜짐 lead browser check of the reset button · 2026. 10. 27. …부터" + "해제" 버튼 → 클릭 시 인라인 "해제하면 모의투자 신호와 추매 검토가 다시 나옵니다. 정말 해제할까요? [해제 확인] [취소]" → 해제 확인 클릭 → `kill_switch_events` 마지막 행 `('reset','manual','','user')` → 규칙 점검 재조회(데모는 예측 추론 포함 약 25초, N-COACH-8) 뒤 칩 "킬스위치 꺼짐"·버튼 사라짐 |

리드가 발견한 문구 문제(비차단, 수정 라운드에 포함): 허용 낙폭 위반 detail의 창 이름 "3y"(= N-COACH-7), 습관 점검 머리글 "25.10.27부터 10.27까지"처럼 창 시작·끝의 연도 표기 불일치, 월간 리뷰 "지금 정책 위반 N건"의 기준(= N-COACH-5).

#### 수정 라운드 재검증 (2026-10-27, verifier)
범위: 리드 요청대로 좁게. 코드·테스트 수정 없음, 서버 없음(TestClient), 데모 DB는 GET만(시작·끝 모두 `policy_settings` 0행·규칙 목표 `{}`·거래 21건·킬스위치 이벤트 2건으로 동일), 실제 DB·`.env`는 읽지 않음. 아래 수치는 모두 `backend/seed`의 데모 데이터다.

**(1) 데모 DB 응답** (`<scratch>/coach_recheck.py`, 출력 `demo_out/r2_*.json`)

| 확인 | 결과 |
|---|---|
| `GET /api/coach/diagnosis` `risk.actual` | **null**. `actual_error` = "단가 확인이 필요한 거래 5건(티커 가림)이 있어 실제 추이의 낙폭을 계산하지 않았습니다. 거래 페이지에서 단가를 고치면 계산됩니다." 598,141%·584,636%는 응답 어디에도 없음 |
| `risk.windows` | 1y `usable=true` rows 251 vol 25.6807% dd 17.2944%, 3y `usable=true` rows 750 vol 26.6498% dd 27.9362%(2025-01-21→2025-04-08). 1차와 소수점 둘째 자리 차이는 현재가가 바뀌어 비중이 달라진 것. `coach_recompute.py`로 다시 독립 재계산 → **117항목 FAIL 0, 차이 0.0**(변동성·swing·낙폭·날짜·상관 14×14·베타 13종목), `actual is None` 분기 출력 |
| 위반 detail | "지금 구성으로 지난 **3년**을 지났다면 가장 깊은 하락이 27.9%로, 적어 둔 허용 낙폭 20%를 넘습니다"(N-COACH-7 닫힘) |
| `GET /api/coach/review?month=2026-10` | `suspicious_trades=5`, `flags_counted=true`, `caveats[0]` = "넣은 돈·시장 손익에 단가 확인이 필요한 거래 5건이 들어 있어 값이 왜곡될 수 있습니다." 입금·시장 손익 수치는 장부대로 그대로(설계: 사실 + 단서, 화면은 무색) |
| `…?month=2025-06` | `suspicious_trades=0`, **`flags_counted=false`**, `caveats[0]` = "습관 점검은 최근 1년 거래만 보므로 이 달의 플래그는 세지 않았습니다."(N-COACH-2) |
| `…?month=2026-09` | `suspicious_trades=0`(단가 오류 행은 10-19라 그 전 달은 깨끗), `flags_counted=true` |
| `GET /api/coach/patterns` `rule_lag` | 282봉 5종목(티커 가림, since 2025-09-12 = 조회 시작) `since_window_start=true`; XRP-USD 293·TSLA 75·SOL-USD 350은 `false`(N-COACH-6) |
| 응답 시간 | 새 프로세스 첫 호출 diagnosis 3.66s(15분 TTL 재동기화 포함), review 0.37~0.75s, patterns 0.31s |

**(2) fail-closed 경로** (`<scratch>/coach_recheck.py` 뒷부분, `<scratch>/coach_recheck2.py`)

| 경로 | 결과 |
|---|---|
| 엔진 직접 호출 `strategy.coach.twr_index(데모 자산 추이, 21건 거래 입금)` | **ValueError** "2026-10-19: 입금을 뺀 수익률이 -100% 이하라 시간가중 지수를 만들 수 없습니다(단가가 틀린 거래가 있는지 거래 페이지에서 확인하세요)" — 1차에서 598,141%를 낸 바로 그 입력이 이제 거부됨 |
| 같은 곡선에 단가 오류 5건을 뺀 입금 | 지수 생성, 최대 낙폭 28.49%(곡선 자체에는 10-19의 점프가 남아 있으므로 참고값) |
| `V_{d−1}==0` | `[0, 100, 110]` → `[1.0, 1.0, 1.1]`(기존 동작 유지) |
| 서비스 경로(필터를 끈 상태) | 프로세스 안에서만 `CoachService._suspicious_trades`를 `[]`로 패치(DB 쓰기 없음) → `risk.actual=null`, `actual_error` = 위 ValueError 메시지 그대로(날짜 2026-10-19 포함), 창 2개 `usable=true`. 즉 20배 필터를 통과하는 단가 오류(예 19배)가 있어도 수십만 % 대신 이유가 나온다 |
| 단위·API 테스트 | `tests/test_coach.py:705-729`(정확히 −100% 거부, 첫 위반일 보고, 음수 거부, 0 구간 재시작), `tests/test_coach_api.py:367-398`(25배 매수 → `actual=null`·"단가 확인 1건 GOOG 거래 페이지", 창 usable 유지, 리뷰 `suspicious_trades=1`·2026-09 깨끗; 1/40배 매도도 걸림) |

**(3) `Coach.tsx`의 `PnL`** — import(26행) 외 사용은 세 곳: 742행 실현손익, 743행 배당, 729행 `result = doubtful ? signedKrw : PnL`(`doubtful = r.suspicious_trades > 0`)이 741행 시장 손익과 754행 벤치마크 초과에 쓰임. 변화·넣은 돈은 `formatKrw` 무색(739-740행). 리밸런싱 표 585행은 `signedKrw(o.realized_pnl_krw_if_sold)`(부호만, `lib/coach.ts:443`). 테스트: `Coach.test.tsx:498-508`(단가 확인 1건이면 시장 손익·벤치마크 초과 무색, 실현손익은 `text-loss` 유지), `coachPhrases.test.ts:240-244`(`signedKrw`에 ▲▼ 없음), `Coach.test.tsx:420`·`coachPhrases.test.ts:158`(`actual_error`를 `actualCurveNote`로 그대로 표시).

**(4) 비차단 항목 닫힘 여부**
- N-COACH-2 닫힘: `services/coach.py:1127` `flags_counted = first_day ≥ today − 1년`, 1144-1145 `FLAGS_OUTSIDE_WINDOW_KO` caveat; `Coach.tsx:776` "습관 점검에 걸린 거래 집계 안 함"; `test_coach_api.py:595-610`(2025-06·2025-10 false, 2025-11 true), `Coach.test.tsx:510-518`; 데모 2025-06 false.
- N-COACH-3 닫힘: `lib/coach.ts:443 signedKrw` → `Coach.tsx:585`; `coachPhrases.test.ts:240-244`.
- N-COACH-4 닫힘: `lib/coach.ts:300-301` `empty` 검사가 `policy_set`보다 먼저; `coachPhrases.test.ts:150-152`(`empty && !policy_set` → undefined).
- N-COACH-5 닫힘(라벨로 기준 명시): `lib/coach.ts:478 reviewViolationsLabel` "지금 비중·자산군 위반 N건" → `Coach.tsx:734`; `coachPhrases.test.ts:281-282`, `Coach.test.tsx:481`. `_violations_now` 계산 방식은 그대로(비중·노출만)이고 라벨이 그 기준을 말한다.
- N-COACH-6 닫힘: `strategy/coach.py:1361 LagFlag.since_window_start`(1486 `days == len(values)`), `schema.d.ts:1967`; `lib/coach.ts:457-461 lagPhrase` "N봉 이상 (조회 범위 처음부터)"; `test_coach.py:1242-1269`, `test_coach_api.py:544-557`, `coachPhrases.test.ts:268-277`; 데모 5종목 true.
- N-COACH-7 닫힘: `strategy/coach.py:89 WINDOW_LABELS_KO`·`window_label_ko`; `test_coach.py:1087`("지난 3년을" 포함·"3y" 없음)·1093-1095; 데모 detail 확인.
- N-COACH-9 닫힘(덤): `strategy/coach.py:90-93 REMAINDER_ZERO_NOTE_KO`(1062·1072행에서 note 추가); `test_coach.py:821-845`(2개(C, D) 표기, 목표 합이 자산군 목표 미만이면 note 없음).
- 리드 발견 연도 표기: `lib/coach.ts:470 windowSpanPhrase` → `Coach.tsx:642`; `coachPhrases.test.ts:257`.
- N-COACH-8 그대로(관찰, 코치 결함 아님).

**(5) 재실행**: backend `pytest -o addopts="" -q` **883 passed**(146s; 1차 875 + 8), `ruff check .` All checks passed, `ruff format --check .` 143 files already formatted. frontend `npm test -- --run` **33 files / 220 tests passed**(1차 210 + 10), `oxlint` 0, `build` 통과, `gen:api` 전후 sha256 동일(`openapi.json` 0bc560cb…, `schema.d.ts` 53646995…) — 커밋된 두 파일이 재생성 결과와 일치.

**남은 관찰(비차단, 새 번호)**
- N-COACH-10(권고): `_price_suspicious`의 경계값(정확히 20배)과 `_suspicious_trades`의 분할 비율 복원(`split_events`, `services/coach.py:492-495`)에 직접 테스트가 없다(API 테스트는 25배·1/40배만). 분할 이전 거래가 있는 종목에서 20배 규칙의 거짓 양성·음성이 생겨도 테스트가 잡지 못한다. 분할 종목 하나로 "분할 전 거래는 정상, 복원 없이 보면 걸림"을 고정하는 테스트를 권고.
- 월간 리뷰의 입금·시장 손익은 단가 오류가 있어도 장부 그대로(데모 2026-10 수천억 원) 내려온다. 설계(ISSUE-048 해결 ②: 사실은 두고 단서 + 무색)와 일치하므로 허용. 근본 해결은 사용자의 단가 수정(TODO_FOR_ME).

**재검증 판정: 통과.** N-COACH-1(ISSUE-048)은 두 겹(20배 필터 → `actual_error`, 엔진 fail-closed → `actual_error`)으로 닫혔고, N-COACH-2~7·9도 코드·테스트·데모 응답에서 확인했다. 남은 것은 N-COACH-8(관찰)과 N-COACH-10(테스트 보강 권고)뿐이다.

재현: backend\ `PYTHONPATH=<backend> AM_DATABASE_URL=sqlite:///demo.db py -3.11 -m uv run python -X utf8 <scratch>/coach_recheck.py <scratch>/demo_out` → `… coach_recompute.py demo.db <scratch>/demo_out r2_diagnosis.json` → `… coach_recheck2.py <scratch>/demo_out`; 테스트·린트·빌드 명령은 위 "재현 명령"과 같다.

## 학습 코치 1차 검증 (2026-11-05, verifier)

대상: 미커밋 작업 트리(브랜치 `agent-team`, HEAD b482db8). 사양은 `~/.claude/plans/cozy-noodling-volcano.md` "J. 학습 코치"와 D-034(§8 착수 중 결정 포함). 범위는 코드·API·수치(1차)이며 강의 편수·링크·브라우저 확인은 2차(리드)다. 검증 중 quant-researcher가 `app/learn/content/`에 강의를 계속 추가하고 있었고, 그 영향이 아래 N-LEARN-1이다.

**판정: 조건부 통과 — 차단 후보 1건(N-LEARN-1: 강의 1편의 검증 실패가 `app.main` import를 막아 검증 시간 중 약 50분간 백엔드 전체가 뜨지 않음. 설계상 의도된 fail-closed지만 범위가 `/learn`이 아니라 앱 전체), 수정 권고 2건(N-LEARN-2 손절선 아래 보유 일수가 포지션 시작 전 기간을 포함, N-LEARN-3 `oversizing`이 표본 3건(최소 5)인데 `some`), 비차단 2건(N-LEARN-4·5), 관찰 4건. 재현·마이그레이션·빈 DB API·데모 독립 재계산(차이 0.0)·이번 주 캐시·문구·위생·설계 규칙은 반박 실패로 통과.**

#### 1. 재현(절대 경로, bash; `py -3.11 -m uv`, ISSUE-032)
| 명령 | 결과 | 팀 보고와 대조 |
|---|---|---|
| backend\ `py -3.11 -m uv run pytest -o addopts="" -q -p no:cacheprovider` | **1107 passed, 2 xfailed** in 141.88s (13:4x, 강의 2편 시점) | 보고 1105 + 2 xfailed → 이후 강의 추가로 2건 증가(파라미터화 테스트). 불일치 아님 |
| `ruff check .` / `ruff format --check .` | All checks passed / 160 files already formatted | 보고된 `tests/test_skills.py:450` E501은 이미 고쳐짐 |
| `alembic heads` | `26d32d8e1b7a (head)` 하나 (`down_revision = '8ed46201b220'`) | 일치 |
| frontend\ `npm test -- --run` | **38 files / 255 tests passed** | 일치 |
| `npm run lint` / `npm run build` | oxlint 0건(exit 0) / `built in 266ms`(exit 0) | 일치 |
| `npm run gen:api` | 이 셸에서는 스크립트의 `py -m uv`가 `No module named uv`로 **실패**(ISSUE-032, `VIRTUAL_ENV`). 같은 두 단계를 수동 실행(`python -m app.export_openapi <scratch>/openapi.json` → `npx --yes openapi-typescript@7`)해 작업 트리 파일과 `diff -q` → `openapi.json`·`schema.d.ts` **IDENTICAL**(sha1 `dccc940c…`, `b746e09a…`). `git diff --stat frontend/src/api/`는 HEAD 대비라 항상 4파일 변경으로 나옴 → 재생성 비교로 대신함 | 보고 "diff 없음"과 같은 결론 |

#### 2. 마이그레이션
| 확인 | 결과 |
|---|---|
| 빈 DB(`AM_DATABASE_URL=sqlite:///verify_empty.db`, 새 파일) `alembic upgrade head` | … → 8ed46201b220 → **26d32d8e1b7a**. `sqlite_master`: `upcoming_events`(id PK, symbol VARCHAR(20) NOT NULL, kind VARCHAR(12), event_date DATE, estimated BOOLEAN NOT NULL, fetched_at DATETIME, source VARCHAR(20), **`uq_upcoming_events UNIQUE (symbol, kind, event_date)`**, `ix_upcoming_events_symbol` non-unique), `event_syncs`(symbol PK, fetched_at, error VARCHAR(300) NULL), `lesson_progress`(lesson_id VARCHAR(40) PK, read_at·quiz_score·quiz_total·quiz_at NULL, updated_at NOT NULL) = `db/models.py`와 일치 |
| `alembic downgrade -1` → `upgrade head` 왕복(빈 DB) | 내려가면 세 테이블 사라지고 `alembic_version=8ed46201b220`, 다시 올리면 세 테이블 복귀·`26d32d8e1b7a`. `alembic check` "No new upgrade operations detected." |
| 데모 DB(`backend/demo.db`) `alembic upgrade head` / `alembic check` | 이미 head(이전 세션에서 올라감), "No new upgrade operations detected." 거래 21건(데모 시드 16 + 2026-10-19 가져오기 검증 5건, 단가 오류라 20배 규칙에 걸림), `rule_settings` 1행, `policy_settings` 0행, `corporate_actions` detected 26·ignored 1 |
| 임시 DB | `verify_empty.db`는 검증 뒤 삭제. `demo.db`에는 이번 검증으로 `event_syncs` 10행·`upcoming_events` 14행이 생겼고 `lesson_progress`는 0행 그대로(PUT은 빈 DB에만 보냄) |

#### 3. 빈 DB API(8003, 실제 공급자 `market_provider=yfinance`, `live_trading=False` 확인)
서버는 N-LEARN-1 때문에 작업 트리에서 바로 뜨지 않아, **`backend/app`의 스냅샷 사본(14:27, 당시 검증에 실패하던 `costs_fees_fx_tax.py`·`stop_loss_and_rules.py` 2개만 제외, `diff -rq`로 그 외 동일 확인)**에서 띄웠다(카탈로그 3편: diversification-basics·position-sizing·chasing-buys). 14:40에 작업 트리가 잠시 import 가능해졌을 때 작업 트리에서도 한 번 더 띄워 `skills`·`week`·`lessons`를 재확인했다(그 시점 카탈로그 7편).

| 호출 | 결과 |
|---|---|
| `GET /api/learn/skills` | 200(0.35s). `empty=true`, `trades_total=0`, `window 2025-11-05..2026-11-05`, 9개 습관 **전부 `insufficient`**·`sample_n=0`·`lines=[]`. 거래 기반 7개 caveat = `NO_TRADES_KO`, `class_drift` caveat = `NO_POLICY_KO`, `concentration` caveat None. `loss_holding`·`short_holding`·`concentration`·`class_drift`의 `window_start=None`, 나머지 = 365일 창. `first_topics_source="default"`, `first_topics` = 스냅샷 `['diversification-basics','position-sizing']` / 작업 트리 `['diversification-basics','position-sizing','stop-loss-and-rules']`(카탈로그에 있는 것만) |
| `GET /api/learn/week` | 200(0.22s). `start 2026-11-05 end 2026-11-12`, items = `policy_unset`·`cash_missing`(둘 다 setup, `/coach`)뿐. 휴장일 없음(11-05~11-12 NYSE 정규 개장, 11-11 재향군인의 날은 NYSE 개장이라 맞음). 종목 항목·`stale_symbols`·`errors` 없음 |
| `GET /api/learn/lessons` / `/lessons/chasing-buys` | 200 / 200(`sections`·`references`·`quiz` 3문항·`minutes` 5 포함) |
| `GET /api/learn/lessons/does-not-exist` | **404** `{"detail":"강의를 찾을 수 없습니다 (does-not-exist)","code":"lesson_not_found"}` |
| `PUT /api/learn/progress/chasing-buys {"read": true}` | 200, `read_at` 채워짐, quiz 필드 null |
| `PUT … {"answers": [0,0,0]}` | 200, `quiz_score=1, quiz_total=3, quiz_at` 채워짐(서버 채점; `lesson_progress` 행에 답은 없음) |
| `PUT … {"answers": [0,0]}` | **422** `answers_length` "답은 문항 수(3)만큼 보내야 합니다 (받은 수 2)" |
| `PUT … {}` | **422** `empty_progress` |
| `PUT /api/learn/progress/does-not-exist {"read": true}` | **404** `lesson_not_found` |
| `GET /api/learn/lessons` 이후 | `read_count=1`, 해당 강의 `progress` 채워짐 |

리드 참고(화면): `first_topics`가 비면 `Learn.tsx:FirstTopicsCard`는 `lessons.default_first_topics`로 대체하고 그것도 비면 카드를 숨기며(`return null`), 홈 `LearnCard`는 `learnSummary`가 주제 없이 "공부 목록 N개 →"만 만든다(`lib/learn.ts:144-147`). 지금은 기본 3편이 모두 있어 해당 없음.

#### 4. 데모 DB API·독립 재계산(8002, 실제 공급자; 스크래치 `recalc_demo.py`가 `transactions`·`price_bars(KRW=X)`만 sqlite3로 읽어 재계산)
`GET /api/learn/skills` 200(4.28s, 첫 호출·봉 1년·시세 포함). `trades_total 21 · trades_in_window 11 · suspicious_excluded 5 · window 2025-11-05..2026-11-05`.

| 항목 | 응답 | 재계산 | 차이 |
|---|---|---|---|
| 창 안 거래 수 | 11 | 11(2025-11-05 이후; 2025-11-03 거래는 제외) | 0 |
| 단가 확인(20배) 거래 | 5 | 5(가져오기 5건) | 0 |
| (b) 수수료 bp = Σfee·fx / Σ(qty·price·fx)×1e4 | `cost_blindness.lines[0].value` **6.430387822570605e-05** | **6.430387822570605e-05**(fee 2,185원 / 3.398e11원) | **0.0**(허용 1e-6) |
| (c) 메모 비율 | `no_journal.lines[0].value` 0.0 (11건 중 0) | 0.0(모든 note가 `demo` 또는 `IMPORT_NOTE` → origin manual 0건), 가져온 거래 5건 줄 | 0.0 |
| (d) 보유 종목 수 | `concentration.sample_n` 14 | 14 | 0 |
| (d) top1 | VOO 21.19%(상한 20%) | 규칙 점검 `weight_pct` 21.1879와 동일 값(`weights()` 재사용) | 0 |
| (a) 라운드트립 | `short_holding` n=0(닫힌 트립 없음), 열린 포지션 나이 717·697·667·617·567·517·467·397·367·17×5일 | 닫힌 트립 0(AAPL·NVDA·SOL 부분 매도만), 같은 나이 | 0 |
| (a) 매도 결과 | `loss_holding` n=3 "손실 매도 1건 · 이익 매도 2건", 재매수 0 | NVDA gain(300일)·AAPL gain(580일)·SOL-USD loss(290일) | 일치 |

레벨을 `SkillThresholds` 기본값으로 손확인: `no_journal` 0/11=0 < 0.20 → **strong**(n 11 ≥ 5) ✓ / `concentration` top1 21.19 > 20(+EPS)이고 ≤ 30, 실질 종목 수 8.78 ≥ 3, 코인 25.7 ≤ 30 → **some** ✓ / `rule_breaking` n = 추가 매수 3 + 점검 포지션 14 = 17, lag 7개·물타기 0 → **some** ✓(정책 미저장이지만 규칙 저장됨이라 `NO_RULES_KO` 없음 ✓) / `chasing` 0/8 → **none**(n 8 = 창 안 매수 8 − 봉 없음 0) ✓ / `class_drift` 정책 없음 → **insufficient** + `NO_POLICY_KO` ✓ / `cost_blindness` 수수료 기록 2/11 = 18% < 50% → bp 포기 + `NO_FEES_RECORDED_KO`, 과매매 달 0 → **insufficient** ✓ / `loss_holding` n 3 < 4 → **insufficient** ✓ / `short_holding` n 0 < 3 → **insufficient** ✓ / `oversizing` n 3(창 안 매수 8 − 첫 매수 없음 − 단가 확인 5) → 표본 부족인데 응답은 **some**(N-LEARN-3). 순서 strong → some → none → insufficient ✓. `first_topics` = ranking `['diversification-basics','position-sizing']`(strong `no_journal`의 trade-journal과 some `rule_breaking`의 stop-loss-and-rules가 스냅샷 카탈로그에 없어 빠짐; 로직 ✓). 모든 줄에 `n`이 있음(`n is None` 0건). 창: 365일 습관 5개 = `2025-11-05..2026-11-05`, 전 기간 2개 = `2024-11-18(첫 거래)..2026-11-05`, 오늘 상태 2개 = `None..2026-11-05` ✓. `caveats` = 단가 확인 5건 제외 안내 1건.

#### 5. 이번 주 볼 것 — 지연·캐시(8002)
| 확인 | 결과 |
|---|---|
| `GET /api/learn/week` 1·2·3회 | 200 **1.03s / 0.56s / 0.47s**. 첫 호출에 yfinance `Ticker.calendar` 10종목(주식 5 + 가져오기 5)을 8 워커 병렬로 받음. 서버 로그에 VOO "No fundamentals data found"(yfinance 자체 출력)가 있으나 빈 달력으로 성공 처리돼 `error=None`(ETF라 실적 없음, 맞음) |
| `event_syncs` | 10행(주식만), `fetched_at` 전부 `05:30:57.651247`(한 트랜잭션·한 `now`), `error` 전부 None. 2·3회차 뒤에도 **변화 없음**(TTL 안 재요청 없음) |
| `upcoming_events` | 14행, 전부 주식 심볼·`source=yfinance`·`estimated=0`. **코인(`BTC-USD`·`ETH-USD`·`XRP-USD`·`SOL-USD`) 행 0**. 지난 날짜(배당락 09-04·09-10·10-14, 실적 10-29)도 저장되고 `upcoming()`이 `date >= today`로 거름(설계대로) |
| items(20개) | now 13(`suspicious_trade` 5건 → `/transactions?check=1`, `pending_action` 26건, `rule_triggered` 11종목 — 규칙 점검 `label_ko` 재사용) → soon 4(실적 11-06·11-10·11-10, AAPL 배당락 11-12, 창 밖 11-18·11-19는 제외 ✓) → setup 3(`policy_unset`·`cash_missing`·`near_cap` VOO 0.0%p). `(심각도, date or today, symbol)` 정렬 **True**. 응답 3회 전부 동일(`week1 == week2 == week3`) |
| `stale_symbols` / `errors` | `[]` / `[]` |
| `lesson_id` | `near_cap` → position-sizing만 채워짐(나머지 종류의 강의가 아직 없음, 2차에서) |

#### 6. 문구·정직성 grep(Grep 도구; ripgrep은 `(?!…)`를 지원하지 않아 `수익(을|이)?\s?보장`은 따로 검색해 "하지 않"을 눈으로 제외)
| 대상 | 결과 |
|---|---|
| `app/learn/**`, `strategy/skills.py`, `services/learn.py` — 금지어·등급어 | 정규식 정의(`model.py:61-65`), docstring 열거(`skills.py:16-18`), 고지문 `LEARN_DISCLAIMER_KO`·`chasing_buys.py:54` "수익을 보장하지 않"만. 사용자 문장 위반 **0** |
| `lib/learn.ts`, `Learn.tsx`, `Lesson.tsx`, `LearnCard.tsx`, `SkillChip.tsx`, `LessonBody.tsx`, `ReferenceList.tsx`, `Quiz.tsx` | 정규식 정의(`learn.ts:30-31`)·주석·`LEARN_HONESTY_KO`만. "점수"는 화면 문구에 없음(`progressLabel` "셀프 체크 2/3", `quizResultPhrase` "N문제 맞았어요") |
| 같은 8개 파일의 `PnL`·▲·▼·`text-gain`·`text-loss` | `learn.ts:10` 주석("no ▲▼") 1건뿐 |
| `strategy/skills.py`·`services/learn.py`의 `execute(`·`Broker`·`KillSwitch` | 0건(`test_skills.py:860-872`가 소스 토큰 금지로 고정, `AM_LIVE_TRADING` 포함) |
| `services/learn.py`·`services/events.py`·`deps.py`의 Fake | `learn.py`·`events.py` 0건. `deps.py`는 `market_provider == "fake"`일 때만 `FakeProvider`(49행), `AM_IMPORT_EXTRACTOR=fake`일 때만 `FakeExtractor`(127행); `get_learn_service`는 같은 공급자에 `source="fake"/"yfinance"` 표시 |
| `yfinance` import | `app/data/yfinance_provider.py:13` 한 곳(`deps.py:52`는 주석) |
| `AM_LIVE_TRADING` | `git diff`(추적 파일) 0건. 미추적 파일에서는 `test_skills.py:871`(금지 토큰 목록)·`coach.py:8` docstring뿐. 스냅샷 서버 `settings.live_trading=False` |

#### 7. 공개 저장소 위생
새 테스트 5개의 티커 토큰: AAA 212·BBB 103·CCC 22·DDD 8·ZZZZ 3(합성), AAPL 6·MSFT 5·BTC-USD 9·ETH-USD 1·KRW-BTC 7·KRW-SOL 1·BRK-B 1(기존 코치 테스트 `seed_mixed`·FakeProvider 값). `DECISIONS.md`·`PROGRESS.md` 추가분에 티커·금액 없음. `git status`에 `*.db`·`.env`·`backend/artifacts/`·`.claude/`·`frontend/.vitest/`·로그 없음(`git check-ignore -v`: `*.db`, `.env`, `backend/artifacts/`, `.claude`, `frontend/.gitignore:27 .vitest/`, `backend/.dev-backend*.log`). `backend/scripts/__pycache__`는 `__pycache__/`로 무시. 통과. 이 절의 수치는 데모 시드와 합성값만 쓰고 가져오기 검증 5건의 심볼은 적지 않는다.

#### 8. 설계 규칙(코드 읽기)
| 규칙 | 확인 |
|---|---|
| `week()`가 `CorporateActionService.detect()`를 부르지 않음 | `services/learn.py`에 `detect(`·`diagnosis(` 0건. `pending`은 `select(func.count()).where(status == DETECTED)`(696-703행) |
| `skills()`가 `diagnosis()` 위가 아님 | `coach._habits(today)`(564행) + `rules.check_all()` + 순수 함수 |
| `EventService.refresh` 네트워크 → 쓰기 순서 | `ThreadPoolExecutor(min(8, n)).map(_fetch)`가 끝난 뒤에야 `_replace_rows`·`event_syncs` upsert·`commit()`(76-97행) |
| 공급자 실패 시 마지막 값 유지 + stale | 코드 81-87행(실패면 행 유지·`fetched_at` 유지·`error` 기록), `tests/test_events.py::test_failed_fetch_keeps_rows_reports_error_and_retries`·`test_first_fetch_failure_records_error_without_rows` 존재·통과 |
| `TradeView` 기본값 | `fee=0.0`, `fx_krw=None`, `origin="manual"`, `note=None`(`strategy/coach.py`); 기존 `test_coach*`가 전체 통과에 포함 |
| 거래 0건의 `rule_breaking` | 빈 DB 응답 `insufficient`·n 0·`NO_TRADES_KO`(서비스가 `_insufficient`로 만듦) |
| 무효화 | `hooks.ts`: 거래·규칙·정책·킬스위치·배당/분할 mutation 7곳에 `['learn']` 무효화, 학습 훅 키 `['learn', …]` staleTime 5분 |

#### 발견한 문제(ISSUE 형식, 번호는 리드가 부여)

### [N-LEARN-1] 강의 1편의 검증 실패가 백엔드 전체 import를 막는다(검증 중 약 50분)
- 현상: 13:51(`costs_fees_fx_tax.py` 2,644자 > 1,800)부터 14:36까지, 그리고 14:40 이후 다시(새 강의의 금지어 "section … contains banned wording"), `app.main` import가 `ValueError`로 실패. 그 동안 `uvicorn`(8002·8003 모두 exit 1), `python -m app.export_openapi`, `pytest`(`deps.py` → `services/learn.py` → `catalog.py`를 거치는 모든 테스트) 전부 불가. 홈·거래·코치 등 학습과 무관한 모든 API 포함.
- 원인: `app/learn/catalog.py:61`이 모듈 import 시점에 `_load()`로 모든 강의를 만들고, `model.py`의 `__post_init__`이 실패하면 예외가 `deps.py` import까지 전파된다. D-034 §8이 "의도된 fail-closed"로 적었지만 그 범위가 `/learn`이 아니라 앱 전체다.
- 근거: 스크래치 `server_8002.log`·`server_8003.log`(Traceback `catalog.py:52 → model.py:312 ValueError`), `check_content_modules.py` 14:26 결과(OK 3 / BAD 2: costs 2,025자·stop-loss 1,871자), 14:36 OK 5, 14:40 `pytest tests/test_learn_content.py` 금지어 실패.
- 해결: (비움 — 리드 판단) 후보: ① 콘텐츠 검증 실패를 `/learn` 범위로 한정(카탈로그는 유효한 강의만 들고 실패 목록을 보관 → `LearnService`가 실패가 있으면 학습 라우트만 503/`errors`로 닫음; 다른 라우트는 영향 없음) ② 최소한 콘텐츠 작업 절차에 "저장 전 `pytest tests/test_learn_content.py`"를 강제(D-034 §8에 이미 적혔지만 지켜지지 않음).
- 검증: 이번 1차는 유효 강의만 둔 스냅샷에서 API를 확인했고, 작업 트리가 import 가능해진 14:40 시점에 빈 DB 호출을 재확인함. 수정 뒤 verifier 재확인 필요. 담당 추정: quant-researcher(절차) + 리드/app-engineer(①의 설계).

### [N-LEARN-2] `rule_breaking` 줄의 "손절선 아래 머문 일수"가 포지션이 생기기 전 기간을 포함한다
- 현상: 데모 응답 `rule_breaking.lines[1]` = "손절선 아래에 머문 채 들고 있는 종목 7개 (… 283일 이상 …)"에서 2026-10-19에 처음 산(17일째) 5개 포지션이 "283일 이상"으로 나온다. `short_holding` 줄은 같은 종목을 "17일째"로 적어 한 응답 안에서 모순된다.
- 원인(확인): `strategy/coach.py:1478 rule_lag`는 `(symbol, avg_cost, cut_pct)`만 받아 조회 시작(`window_start − PATTERN_BARS_MARGIN`)부터의 종가 전부를 센다. 포지션 시작일을 모르므로 매수 전 종가가 손절선 아래이면 그 기간도 "머문" 것으로 센다(가져오기 단가 오류가 아니어도, 고점 매수 뒤 15% 하락처럼 매수 전 1년 종가가 손절선보다 낮았던 경우에 같은 일이 난다). 코치 페이지는 N-COACH-6에서 "N봉 이상 (조회 범위 처음부터)"로 한정어를 붙여 닫았지만, 학습의 `LAG_DETAIL_KO = "{sym} {days}일{more}"`(`skills.py:101`)는 "봉"을 "일"로 바꾸고 한정어를 뺐다.
- 근거: 데모 `skills.json`·`patterns.json`(`rule_lag` 5종목 `days=283, since_window_start=true`), 거래 테이블의 첫 매수일 2026-10-19.
- 해결: (비움) 제안: `_habits`가 `replay`/`open_since`의 포지션 시작일을 넘겨 `rule_lag`가 시작일 이후 종가만 세거나, 적어도 학습 줄에서 `min(days, 보유일)`로 잘라 "N봉 이상(조회 범위 처음부터)" 한정어를 복원. 담당 추정: risk-engineer(`skills.py` 문구·클리핑, 엔진 `rule_lag` 시그니처), app-engineer(`services/coach.py` 호출).
- 검증: 미수정.

### [N-LEARN-3] `oversizing`이 표본 3건(최소 5)인데 `some`으로 나온다
- 현상: 데모 `oversizing`: `sample_n=3, min_sample=5, level="some"`, 줄 "손절선까지 손실 합 9.9% (한도 8%)". 화면은 "조금 보임 · 표본 3건"이 된다.
- 원인(확인): `skills.py:683-698` — `_level_for`가 n < min_sample로 `insufficient`를 낸 뒤 `total_risk_pct > max_total_risk_pct`이면 `_at_least(level, "some")`가 표본과 무관하게 `some`으로 올린다. `SkillEvidence` docstring("`sample_n` below `min_sample` makes it `insufficient`")과 D-034 §8의 `rule_breaking` 선례("`some` 바닥은 표본이 `min_sample` 이상일 때만")와 어긋난다. 총 손실 한도는 표본이 아니라 오늘 상태의 사실이라 줄 자체는 맞다.
- 근거: 데모 `skills.json`, `tests/test_skills.py`에 이 경계(표본 부족 + 총 손실 초과) 테스트 없음.
- 해결: (비움) 제안: `rule_breaking`과 같이 `n >= th.min_sample`일 때만 바닥 적용(줄은 그대로 남김), 또는 총 손실 초과를 오늘 상태 항목으로 분리. 담당 추정: risk-engineer(+ evaluation-engineer 테스트).
- 검증: 미수정.

### [N-LEARN-4] (비차단) `cost_blindness` bp 분모에 단가 확인 거래가 들어간다
- 현상: 데모 "거래 비용 합 2,185원 = 거래 금액의 0.00%"(bp 6.4e-05). 단가 확인 5건(가격이 실제의 수천 배)을 빼면 분모 3.398e11원 → 1.600e7원, **1.3654bp**.
- 원인(확인): `cost_blindness_evidence`(`skills.py:858-866`)는 `suspicious_ids`를 받지 않는다. D-034는 단가 확인 거래를 "크기·결과 증거"에서만 빼기로 했고 비용은 언급이 없다.
- 근거: 스크래치 `bp_clean.py`(위 수치). 이번 데모는 수수료 기록 부족으로 레벨에는 영향이 없었지만 줄의 숫자는 그대로 보인다.
- 해결: (비움) 제안: bp 합에서 `suspicious_ids` 제외 + `excluded_suspicious` 보고. 담당 추정: risk-engineer.
- 검증: 미수정.

### [N-LEARN-5] (비차단) 정책 미저장 시 `class_drift`의 현재 상태 줄이 `n=0`이라 화면에 "표본 0건"이 붙는다
- 현상: 데모 `class_drift.lines[0]` = "지금 주식 74.3% · 코인 25.7%", `n=0`. `lib/learn.ts:116 skillLine`은 `n`이 null이 아니면 "· 표본 N건"을 붙이므로 "표본 0건"으로 보인다.
- 원인(확인): `skills.py:589` `EvidenceLine(..., n=0)`. 오늘 상태 줄은 표본이 아니라 `n=None`이 맞다(다른 오늘 상태 줄은 보유 종목 수를 n으로 씀).
- 해결: (비움) `n=None` 또는 보유 종목 수. 담당 추정: risk-engineer.
- 검증: 미수정.

**관찰(비차단)**
- `EventService._stale`(`events.py:175`)은 `error is not None`이면 TTL과 무관하게 다음 요청마다 다시 받는다(테스트가 그 동작을 고정). 배당·분할 감지("실패한 종목은 다음 요청에서 재시도")와 같은 선례라 허용하되, 홈 `LearnCard`가 5분마다 `/week`를 부르므로 계속 실패하는 심볼(상장폐지·오타 티커)이 있으면 yfinance 요청이 5분마다 나간다. 10분 백오프(의원 거래 선례)를 고려할 만하다.
- VOO가 상한 20%로 계산돼 `concentration some`·`near_cap 0.0%p`가 된다. `strategy/risk.py:40 INDEX_FUNDS = {"SPY"}`(D-025 "넓히려면 새 결정")라 학습 코치 결함이 아니다. 리드가 D-025 범위 결정 시 참고.
- `npm run gen:api`의 `py -m uv`는 `VIRTUAL_ENV`가 잡힌 셸에서 실패한다(ISSUE-032와 같은 원인). 스크립트를 `py -3.11 -m uv`로 바꾸거나 CLAUDE.md에 적어 두면 재발을 막는다.
- `week()`의 `rule_triggered` 11건 중 5건은 가져오기 단가 오류 포지션(평균단가가 실제의 수천 배라 항상 "손절 검토")이다. 설계대로 규칙 점검 결과를 그대로 옮긴 것이며, 단가를 고치면 사라진다(`suspicious_trade` 항목이 그 안내를 한다).

재현: backend\ `py -3.11 -m uv run pytest -o addopts="" -q` / `ruff check .` / `ruff format --check .` / `alembic heads`; `AM_DATABASE_URL=sqlite:///verify_empty.db py -3.11 -m uv run alembic upgrade head` → `downgrade -1` → `upgrade head` → `alembic check`; 서버 `AM_DATABASE_URL=sqlite:///C:/…/backend/demo.db py -3.11 -m uv run uvicorn app.main:app --port 8002`(빈 DB는 8003) 뒤 `curl http://127.0.0.1:8002/api/learn/{skills,week,lessons}`; 재계산 `py -3.11 -I <scratch>/recalc_demo.py demo.db 2026-11-05 <scratch>/demo/skills.json`, `py -3.11 -I <scratch>/bp_clean.py demo.db`; frontend\ `npm test -- --run` / `npm run lint` / `npm run build`; gen:api는 `cd backend && py -3.11 -m uv run python -m app.export_openapi <out>.json && cd ../frontend && npx --yes openapi-typescript@7 <out>.json -o <out>.d.ts` 뒤 `diff -q`. 정리: 8002·8003 프로세스 종료(`taskkill`), `verify_empty.db`·스냅샷 삭제 확인.

추기(검증 종료 시점): 리드가 `ISSUES.md`에 등록한 **ISSUE-050**(강의 한 편의 글자수 초과가 앱 전체 import를 막음)이 위 N-LEARN-1과 같은 현상이다(N-LEARN-1 → ISSUE-050). **ISSUE-049**(`test_gurus_api.py`의 고정 날짜 의존)는 이번 재현에서 `AS_OF = date.today() − 1`로 바뀐 테스트가 통과했음을 확인했다. N-LEARN-2~5는 번호 미부여. 정리 확인: 8002·8003 리스너 없음, `verify_empty.db`·스냅샷 삭제, `demo.db`는 `event_syncs`·`upcoming_events` 캐시 행만 추가된 채 유지.

## 학습 코치 2차 검증 (2026-11-06~09, verifier)

대상: 미커밋 작업 트리(브랜치 `agent-team`, HEAD b482db8). 1차(위 절) 뒤 바뀐 것: N-LEARN-1(강의 단위 fail-closed·`catalog.LESSON_LOAD_ERRORS`·`GET /api/learn/lessons`의 `load_errors`·`caveats`), N-LEARN-2~5(`skills.py` 문구·바닥·단가 확인 제외·오늘 상태 표본), 재매수 비율 분모(`loss_holding_evidence(..., rebuy_window_start=)`), `EventService.error_ttl`(1시간, `event_syncs.error` = "<ISO 시도 시각> <메시지>"), 강의 14편 완성(본문 상한 1,800자), `gen:api` 스크립트 `py -3.11 -m uv`, `test_gurus_api.py` 상대 날짜. 검증은 2026-11-06에 수행했고 세션이 끊겨 기록은 11-09에 적었다(스크래치 `scratchpad/verifier/r2_*`에 남은 산출물 기준이며, 재실행하지 않은 항목은 그렇게 적었다). 사용자 확인용 8001·5173 서버와 실제 DB는 건드리지 않았다(8002 데모·8003 빈 DB만 사용, 검증 뒤 종료·임시 DB 삭제 확인).

**판정: 통과(브라우저 확인 제외) — N-LEARN-1~5 모두 해소 확인. 새 발견은 경미 1건(N-LEARN-6, 강의 각주 위치)뿐이고 차단 항목 없음. 화면(`/learn`·`/learn/:lessonId`·홈 `LearnCard`)은 미실시라 사용자 확인이 필요하다.**

#### 1. 재현(절대 경로, bash; `py -3.11 -m uv`, ISSUE-032)
| 명령 | 결과 | 팀 보고와 대조 |
|---|---|---|
| backend\ `py -3.11 -m uv run pytest -o addopts="" -q -p no:cacheprovider` | **1261 passed** in 141.90s (xfail 없음) | 보고 "1,100대" → 강의 12편 추가·새 테스트로 증가. 불일치 아님 |
| 파일별 `pytest -o addopts="" -q tests/test_skills.py` 등 | `test_skills.py` **46** · `test_skills_math.py` **79** · `test_learn_content.py` **189** · `test_events.py` **41** · `test_learn_api.py` **23** | 다섯 수치 모두 일치 |
| `ruff check .` / `ruff format --check .` | All checks passed / 172 files already formatted(1차 160 → 강의 12편 추가) | 일치 |
| `alembic heads` / 데모 DB `alembic check` | `26d32d8e1b7a (head)` 하나 / "No new upgrade operations detected." | 일치. 마이그레이션 자체는 1차에서 왕복 확인했고 이번에 변경 없음 |
| frontend\ `npm test -- --run` | **38 files / 257 tests passed**(1차 255 → +2) | 일치 |
| `npm run lint` / `npm run build` | oxlint 0건(exit 0) / `built in 371ms`(exit 0) | 일치 |
| `npm run gen:api` | **성공**(exit 0, "Wrote ..\frontend\src\api\openapi.json" → openapi-typescript 7.13.0). 실행 전후 `openapi.json`·`schema.d.ts` sha1 동일(`e4c07207…`/`8aec397d…`) → 스키마와 생성물이 맞다 | 1차 실패(ISSUE-032)가 스크립트 `py -3.11`로 해소됨. `git status --short frontend/src/api`는 `M client.ts/hooks.ts/openapi.json/schema.d.ts` 4건인데, 이는 HEAD b482db8에 학습 코치가 아직 없어서이지 gen:api 결과가 달라서가 아니다(해시 동일이 근거). 커밋 뒤에는 비어야 한다 |

#### 2. 강의·fail-closed 범위
| 확인 | 결과 |
|---|---|
| 강의 파일 수 | `backend/app/learn/content/*.py` 14편(`chasing-buys, costs-fees-fx-tax, crypto-specifics, diversification-basics, earnings-week, ex-dividend-date, fx-and-dollar-assets, handling-losses, holding-period-turnover, position-sizing, reading-forecasts, rebalancing-bands, stop-loss-and-rules, trade-journal`) |
| 작업 트리 `LESSON_LOAD_ERRORS == {}` | 데모 8002 `GET /api/learn/lessons`: `total 14`, `load_errors []`, `caveats []`. `test_learn_content.py` 189건 통과(그 안의 `LESSON_LOAD_ERRORS == {}` 단언 포함) |
| 참고 링크 | `PYTHONPATH=. py -3.11 -m uv run python scripts/check_lesson_links.py` → **46/46 references answered 200 (38 unique URLs)**, exit 0. 보고와 일치 |
| 콘텐츠 금지어 | 14편 전체에서 금지 식 매치는 `chasing_buys.py:52` "수익을 보장하지 않지만" 하나이고 lookahead `(?!하지 않)`로 허용되는 문장이다. 등급어(`실력|점수|등급|레벨`) 0건 |
| 깨진 강의 시뮬레이션(**복사본**) | `backend/app`을 스크래치 `snap2`로 복사해 두 편만 고장: `trade_journal.py` 끝에 `LESSON = replace(LESSON, takeaway_ko=… + " 추천")`(금지어), `earnings_week.py` 끝에 `raise RuntimeError("verifier: simulated import failure")`(import 실패). `PYTHONPATH=<snap2>`·빈 DB(`verify_empty.db`)·실제 공급자로 8003에 기동 → **서버가 뜬다**(1차에는 앱 전체가 죽던 상황). 서버 로그에 `lesson trade-journal failed to load and is not served: ValueError: … banned wording: ['추천']`, `lesson earnings-week failed to load and is not served: RuntimeError: …` 두 줄 |
| 8003 응답 | `GET /api/learn/lessons` 200: `total 12`, `load_errors` = `[{earnings-week, "RuntimeError: verifier: simulated import failure"}, {trade-journal, "ValueError: lesson 'trade-journal' contains banned wording: ['추천']"}]`, `caveats` = ["강의 2편을 불러오지 못했어요. 목록에서 빠져 있습니다(개발 중 오류)."], `default_first_topics` 3개. `/lessons/trade-journal` **404** `lesson_not_found`, `/lessons/earnings-week` **404**, `/lessons/chasing-buys` **200**. `/learn/skills` 200(빈 DB: 습관 9개 모두 `insufficient`, `first_topics_source=default` 3개), `/learn/week` 200. 다른 라우트도 살아 있음: `/portfolio/summary`·`/portfolio/holdings`·`/transactions`·`/coach/policy`·`/coach/diagnosis`·`/rules/check`·`/corporate-actions` 모두 200 |
| 화면 단서 | `frontend/src/pages/Learn.tsx:232`가 `data.caveats`를 `<Caveats>`로 그리므로 위 문장이 목록 화면에 보인다(코드 확인, 화면은 미실시) |
| 실제 콘텐츠 보존 | 작업 트리 `backend/app/learn/content/`는 `??`(신규)만이고 내가 고친 것은 `snap2` 사본뿐. `snap2`·`verify_empty.db`는 11-09에 삭제 확인 |

→ **N-LEARN-1(= ISSUE-050) 해소**: fail-closed가 "앱 전체"에서 "그 편만"으로 좁혀졌고, 빠진 편은 API·화면 단서·로그·CI(189건 테스트) 네 곳에 드러난다.

#### 3. 데모 DB 독립 재계산(8002, `AM_DATABASE_URL=sqlite:///demo.db`, 실제 공급자, 2026-11-06)
입력: 거래 21건(데모 시드 16 + 2026-10-19 가져오기 검증 5건), 1년 창 2025-11-06~2026-11-06에 11건, 20배 규칙 단가 확인 5건(가져오기 검증 5건과 일치). 스크래치 `recalc_demo_r2.py`가 sqlite를 직접 읽어 `skills.json`과 대조했다. 응답 시간 `skills` 4.18s(1년 봉 조회 포함), `week` 1.07s → 두 번째 0.58s(이벤트 24시간 TTL 적중).

| 항목 | API | 독립 계산 | 결과 |
|---|---|---|---|
| (a) `cost_blindness` bp | 1.3654008136694085 bp, `excluded_suspicious=5`, 줄 "단가 확인이 필요한 거래 5건은 비용 계산에서 뺐어요", n=6, `insufficient`(수수료 기록 2/6 < 50% → `NO_FEES_RECORDED` 단서) | 수수료 2,185원 / 거래 금액 16,002,627원(단가 확인 5건 제외) = **1.3654 bp**, 차이 0.0 | **일치** → N-LEARN-4 해소(1차 6.4e-05 bp, 분모 3.398e11원 오류가 사라짐) |
| (b) `rule_breaking` 손절선 아래 보유 줄 | 가져오기 검증 5건 포지션(보유 18일) "… 284봉 이상(조회 범위 처음부터)", XRP-USD "303봉"(보유 468일), SOL-USD "360봉"(보유 398일) | 조회한 봉 범위 첫날부터 아래였으면 `since_window_start`로 "이상" 라벨이 붙는지: 18일 보유 종목에 "284봉 **이상(조회 범위 처음부터)**" → 봉 수 ≠ 보유일이 라벨로 설명됨. 468·398일 보유 종목은 "이상" 없이 실제 봉 수 | **모순 해소** → N-LEARN-2 해소(`short_holding` "18일째"와 같은 화면에서 어긋나지 않음) |
| (c) `oversizing` | `sample_n=3`(min 5), level **`insufficient`**, 1차에 있던 "손절선까지 손실 합 …(한도 8%)" 줄은 이번 응답에 없음(표본 부족 시 총 손실 바닥을 적용하지 않는 코드 `skills.py:713-714` 확인) | 1년 창 매수 3건 → n=3 | **일치** → N-LEARN-3 해소 |
| (d) `class_drift`·`concentration` | `class_drift` `sample_n=14`, 줄 `n=14`; `concentration` `n=14`; `n==0`인 줄 없음 | 보유 종목 14개 | **일치** → N-LEARN-5 해소 |
| (e) `loss_holding` 재매수 줄 | "최근 365일 손실 매도 1건 중 0건은 10일 안에 다시 샀어요", value 0.0, n=1 | 창 안 손실 매도 1건, 10일 내 재매수 0건 → 0/1 | **일치**, 분모가 창 안 손실 매도라 100%를 넘을 수 없음(`rebuy_window_start` 확인) |
| 그 외 | `no_journal` strong 0/11, `concentration` some(VOO 21.6% vs 상한 20%, 유효 종목 수 8.5, 코인 25.6%), `chasing` none 0/8, `loss_holding` n=3/4 insufficient("손실 매도 1건 · 이익 매도 2건"), `short_holding` n=0(미청산)에 보유 일수 718/698/668/618/568/518/468/398/368/18×5 | 메모 없는 거래 11/11, 라운드트립 3건, 매도 3건, 보유 일수 전부 내 계산과 동일 | **일치** |
| `first_topics` | `['trade-journal', 'diversification-basics', 'stop-loss-and-rules']`(`source=ranking`) | strong(no_journal) → some(concentration) → 나머지 순서 | **일치** |
| `week` | 두 번 호출 결과 동일(`week1 == week2`), 정렬 `(severity, date, symbol)` 확인 True, `stale_symbols []`·`errors []` | — | 통과 |
| DB 부작용 | `event_syncs` 주식 10행, 단일 `fetched_at 2026-11-06 09:03:47`, `error` 전부 None; `upcoming_events` 주식 14행; `lesson_progress` 0행 그대로 | — | 데모 DB에만 캐시 행 추가 |

#### 4. 일정 재시도(`error_ttl`)
- 데모 DB에는 실패 행이 없었다(`event_syncs.error` 전부 None). VOO는 서버 로그에 yfinance의 `HTTP Error 404 … No fundamentals data found for symbol: VOO`가 찍혔지만 yfinance가 빈 달력으로 돌려주어 성공 행(이벤트 0건)으로 저장됐다 — ETF라 정상이고 24시간 뒤 다시 받는다(참고: 이 경우 공급자는 404와 "일정 없음"을 구분하지 못하는데 yfinance 동작이라 학습 코치 결함으로 보지 않음).
- 따라서 재시도 동작은 테스트로 확인했다(`tests/test_events.py` 360~474행, 41건 통과): `test_failed_fetch_keeps_rows_reports_error_and_retries`(378~382행 `p.event_calls == calls_before` → **error_ttl 안에서는 네트워크 호출 0건**, 385~388행 `DEFAULT_ERROR_TTL` 경과 뒤 재시도), `test_first_fetch_failure_records_error_without_rows`, `test_failed_symbol_waits_error_ttl_but_stays_stale_meanwhile`(error_ttl=30분으로 5…29분 루프마다 호출 수 불변·`stale ["AAA"]`에 메시지 유지, 30분에 재시도, 계속 실패하면 시도 시각이 갱신되어 60분에 다시), `test_error_row_without_attempt_time_is_retried_once`(시각 접두어 없는 구형 행은 한 번 재시도 뒤 접두어 형식으로 저장), `test_error_prefix_round_trip_and_column_width`.
- 코드 대조: `services/events.py` `DEFAULT_ERROR_TTL = timedelta(hours=1)`, `join_error(attempted_at, message)` → `"<ISO 초 단위> <메시지>"[:ERROR_MAX]`, `split_error`로 분리, `refresh()`는 `_due`(`attempted_at is None or now - attempted_at >= error_ttl`)로 고르고 실패 종목은 `fetched_at`·기존 행을 유지한 채 `error`만 갱신, `upcoming()`의 `errors`는 `split_error(...)[1]`(메시지만) → 1차 관찰("실패 행은 매 요청 재시도") 해소.

#### 5. 콘텐츠 인용 확인(HTTP·코드)
`fetch_pages.py`(urllib, 링크 스크립트와 같은 UA)로 4쪽을 받아 `pages/*.html`에 저장하고 `kw_check*.py`로 본문 문구를 찾았다(모두 200).
| 출처 | 인용한 강의 | 확인된 문구 | 결과 |
|---|---|---|---|
| investor.gov `beginners-guide-asset` | `diversification-basics`·`position-sizing`·`rebalancing-bands` | "at least a dozen carefully selected individual stocks", "diversified at two levels: between asset categories and within asset categories", "every six or twelve months", "relatively infrequent basis", "transaction fees or tax consequences" | 강의가 적은 다섯 주장 모두 원문에 있음 |
| investor.gov `investor-bulletins-15` | `stop-loss-and-rules`·`earnings-week` | "July 13, 2017 Updated August 18, 2026"(참고 자료 note "2017년 발행, 2026년 8월 갱신"과 일치), "The stop price is not the guaranteed execution price … becomes a market order", "triggered by a short-term, intraday price move … substantially worse than the stock's closing price", "can deviate significantly from the stop price" | 각주 [1]/[3]의 주장(체결가 미보장·장중 단기 변동으로 발동·정한 가격보다 훨씬 아래 체결) 확인. 단, "정규장에만 작동하거나 유효기간이 있는 경우가 많으니"(`stop_loss_and_rules.py:56-58`)는 원문에 없음(regular trading/extended/expire/time in force/cancel 0건) — 각주가 그 문장 바로 앞에 붙어 있어 N-LEARN-6 |
| kcie `content_idx=1198` | `diversification-basics` | "분산투자에서 중요한 지표는 바로 '상관계수'", "서로 같이 움직이지 않는 자산끼리 분산투자를 해야 위험이 줄어드는 효과" | 확인 |
| kcie `content_idx=1080` | `costs-fees-fx-tax` | "환전수수료 0.3%, 기타제비용 0.2% … 해외 주식 거래 시 매매금액의 약 1%", "100만 원짜리 해외 주식을 거래할 때마다 환전하며 차익 없이 100번만 거래하면 투자금을 모두 수수료로 내고 0원", "잦은 거래를 할 경우 수수료 등의 비용 또한 생각보다 많이 발생" | 각주 [1]의 "환전까지 되풀이하면 … 원금이 크게 주는 계산 예"·"잦은 거래일수록 비용" 확인. 강의 본문의 "1년에 한 번 vs 매주 약 50번"은 강의 자체의 산술이고 `principle` 섹션에 `%` 없음(규칙 준수). "스프레드: 고시 환율과 실제 적용 환율의 차이"는 강의의 용어 설명이고 원문은 "환전수수료"로만 적음(의미 충돌 없음) |
| `ex-dividend-date` vs 코드 | `services/corporate_actions.py:3` "Dividends are recorded when the user held shares the day before the ex-date", `_shares_before(..., as_of=ex_date - 1일)`(268~270행) | 강의 74~75행 "배당락일 전날 보유하고 있었을 때만 올라오는데 … 실제 입금은 보통 몇 주 뒤" | 감지 기준과 강의 설명 일치 |

#### 6. 위생·문구
| 확인 | 결과 |
|---|---|
| `wording_scan.py`(BANNED·GRADE·▲▼ 정규식, `-X utf8`) 대상 `skills.py`·`services/learn.py`·`services/events.py`·`learn/catalog.py`·`lib/learn.ts`·`pages/Learn.tsx`·`pages/Lesson.tsx`·`components/LearnCard.tsx`·`SkillChip.tsx`·`LessonBody.tsx`·`ReferenceList.tsx`·`Quiz.tsx` | 매치는 **규칙 정의·주석뿐**: `skills.py:16,18`(docstring의 금지어 목록), `learn.ts:6,8,10`(주석), `learn.ts:30,31`(`BANNED_WORDS_RE`·`GRADE_WORDS_RE` 정의). 사용자에게 보이는 문자열 매치 0건, 화면 컴포넌트 7개 0건 |
| `AM_LIVE_TRADING` | `git diff`(추적 파일)에 `live_trading` 설정 변경 없음(문서 문구와 `openapi.json`의 기존 필드 줄 이동만). 8002·8003 모두 `live_trading=False`로 기동 |
| yfinance import 위치 | `backend/app/data/yfinance_provider.py:13` 하나 |
| Fake 경로 | `Fake*`는 `deps.py:49,127`의 설정 조건부뿐. `services/learn.py`·`services/events.py`에 Fake·합성·하드코딩 값 없음. 두 서버 모두 실제 공급자(`market_provider=yfinance`) |
| 저장소 위생 | `git status --short`에 `*.db`·`.env`·`artifacts/`·`.claude/`·`.vitest/`·`*.log` 없음(`check-ignore` 확인). `backend/`의 DB 파일은 기존 `asset_manager.db`·`demo.db`뿐이고 `verify_empty.db`는 삭제됨. `.env`는 읽지 않음 |
| 기록 | 이 절에 실제 보유 종목·수량·금액 없음(데모 시드와 "가져오기 검증 5건"만) |

#### 7. N-LEARN-1~5 해소 여부
| 번호 | 내용 | 판정 | 근거 |
|---|---|---|---|
| N-LEARN-1 (= ISSUE-050) | 강의 1편 오류가 앱 전체 import를 막음 | **해소** | §2 복사본 시뮬레이션: 두 편 고장에도 서버 기동, `/lessons` 200 + `load_errors` 2건 + 단서 문장, 해당 편만 404, 다른 라우트 200, 로그 2줄, CI 단언 유지 |
| N-LEARN-2 | 손절선 아래 보유 "N봉"과 보유 일수가 어긋남 | **해소(라벨)** | §3(b) "284봉 이상(조회 범위 처음부터)"로 뜻이 드러남. 봉 수 자체를 보유 일수로 자르지는 않음 — D-034 설계("조회한 첫 봉부터 아래였으면 `since_window_start`") 그대로 |
| N-LEARN-3 | `oversizing` 표본 3건인데 `some` | **해소** | §3(c) `insufficient`, 바닥은 `n >= min_sample`일 때만 |
| N-LEARN-4 | `cost_blindness` bp 분모에 단가 확인 거래 포함 | **해소** | §3(a) 1.3654 bp 독립 계산과 일치, `excluded_suspicious=5` + 줄 |
| N-LEARN-5 | `class_drift` 줄 `n=0` → "표본 0건" | **해소** | §3(d) `holdings_count` 14로 `sample_n`·줄 `n` 채움, `n==0` 줄 없음 |

1차 관찰 사항도 함께 닫힘: `_stale`가 매 요청 재시도 → `error_ttl` 1시간(§4), `gen:api`의 `py -m uv` → `py -3.11`(§1). 남은 관찰 "VOO가 `INDEX_FUNDS`에 없어 상한 20% 적용"은 D-025 범위 문제라 이번 대상이 아님.

#### 8. 브라우저 확인
미실시 — 리드의 Chrome 확장이 연결되지 않아 화면 확인을 하지 못했다. 사용자 확인 필요(`/learn`·`/learn/:lessonId`·홈 `LearnCard`; 특히 §2의 `caveats` 문장과 §3의 "이상(조회 범위 처음부터)" 라벨이 화면에 그대로 보이는지).

#### 발견 사항

### [N-LEARN-6] (경미, 콘텐츠) `stop-loss-and-rules`의 "정규장에만 작동하거나 유효기간이 있는 경우가 많으니"가 SEC 안내문 각주 옆에 있지만 원문에 없다
- 현상: `backend/app/learn/content/stop_loss_and_rules.py:56-58` "자동 손절 주문은 체결 가격이 보장되지 않고[1] 정규장에만 작동하거나 유효기간이 있는 경우가 많으니, 알림을 받아 직접 주문하는 방식도 둡니다." 각주 [1](investor-bulletins-15)은 "보장되지 않고"까지만 가리키지만, 독자는 뒤 절까지 SEC 근거로 읽기 쉽다.
- 원인(확인): 저장한 원문(2026-11-06 200)에 regular trading/extended hours/expire/time in force/cancel에 해당하는 문구가 없다. 원문이 말하는 것은 "증권사마다 스톱 주문 제공 여부·발동 기준이 다르니 증권사에 확인하라"(brokerage firm 8회)다.
- 근거: 스크래치 `kw_check.py`·`kw_check2.py` 출력(`pages/investor_bull15.html`).
- 해결: (비움) 제안 둘 중 하나 — ① 뒤 절을 원문에 있는 "증권사마다 조건이 달라 증권사 안내를 확인한다"로 바꾸거나, ② 뒤 절은 각주 없이 "증권사마다 다르다"로 완화하고 [1]은 "보장되지 않고" 뒤 그대로 둔다. 내용 검증 규칙(`learn/model.py`)은 숫자가 아닌 주장에는 각주를 요구하지 않으므로 코드 변경 아님. 담당 추정: app-engineer(콘텐츠).
- 검증: 미수정. 차단 아님(강의 내용 자체는 보수적이며 사용자에게 손해를 주는 방향이 아님).

**관찰(비차단)**
- `git status --short frontend/src/api`는 학습 코치가 HEAD에 없어 커밋 전까지 비어질 수 없다. gen:api 정합성은 실행 전후 해시 동일로 확인했고, 커밋 뒤에는 이 명령이 비어야 한다.
- VOO의 yfinance 달력 404는 빈 일정으로 저장된다(§4). ETF에는 맞는 결과이고 TTL 24시간이라 노출이 제한되지만, 일시적 404도 같은 모양이 된다는 점은 공급자 수준 한계로 남는다.
- `oversizing`의 "손절선까지 손실 합" 줄은 표본 5건 이상일 때만 나오게 바뀌어 이번 데모(3건)에서는 그 줄의 수치를 대조하지 못했다. 표본이 충분한 데이터로의 대조는 다음 검증 과제.

재현: backend\ `py -3.11 -m uv run pytest -o addopts="" -q` / `ruff check .` / `ruff format --check .` / `alembic heads`; `AM_DATABASE_URL=sqlite:///demo.db py -3.11 -m uv run alembic check`; `PYTHONPATH=. py -3.11 -m uv run python scripts/check_lesson_links.py`; frontend\ `npm test -- --run` / `npm run lint` / `npm run build` / `npm run gen:api`(전후 sha1 비교); 데모 서버 `AM_DATABASE_URL=sqlite:///demo.db py -3.11 -m uv run uvicorn app.main:app --port 8002` → `GET /api/learn/skills`·`/week`×2·`/lessons`; 깨진 강의 시뮬레이션은 `backend/app` 사본에서 두 편을 고친 뒤 `PYTHONPATH=<사본> AM_DATABASE_URL=sqlite:///verify_empty.db <backend>/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8003`(실제 콘텐츠 불변); 인용 확인은 urllib로 4쪽 저장 후 문구 검색. 검증 뒤 8002·8003 종료, `verify_empty.db`·사본 삭제.

## 배포 1단계 검증 1차 (2026-11-11, verifier)

대상: 계획 K-1 / 결정 D-035(읽기 전용 데모 컨테이너 + 단일 계정 로그인). 코드·설정·문서는 고치지 않았고, 이 절은 항목이 끝날 때마다 이어 적는다(추가만, 기존 내용 수정 없음). 스크립트·로그는 스크래치 `scratchpad/verifier/deploy/`에 있다(저장소 밖).

**이 검증의 전제와 한계**
- 1차 범위 밖(2차에서 본다): `main.py`의 정적 서빙 + SPA fallback, `tests/test_static_serving.py`, CI, 프론트 테스트 일부. app-engineer가 검증 도중(11:11~) `backend/app/main.py`와 새 파일 `backend/app/api/frontend.py`를 고치고 있었다. 아래 결과는 **각 항목에 적은 시각의 작업 트리** 기준이고, 그 영역에서 생긴 일시적 실패는 "진행 중"으로 구분했다.
- 터널(`quick`·`named` profile, cloudflared)은 띄우지 않았다. 터널을 거쳐야만 확인되는 것(Cloudflare가 넣는 `CF-Connecting-IP`, 터널 뒤의 방문자별 요청 제한, cloudflared의 `read_only` 동작)은 **미실시**다.
- `backend/.env`, 실제 DB `backend/asset_manager.db`, `backend/artifacts/`는 열지 않았다. 스크래치 인스턴스는 `Settings.model_config["env_file"] = None`으로 `.env`를 읽지 않게 하고 모든 설정을 환경변수로만 주었다(DB·artifacts 경로가 스크래치가 아니면 시작 전 assert로 중단).
- 스크래치 인스턴스의 외부 서비스(하원 서기국·13F/ARK·GDELT·스크린샷 추출기)는 호출 이름만 기록하고 예외를 던지는 기록용 대역으로 바꿨다(요청이 방어선을 통과해도 외부로 나가지 않게, 그리고 통과 여부를 셀 수 있게). 시세 공급자는 `AM_MARKET_PROVIDER=fake`의 `FakeProvider`를 호출 기록 래퍼로 감쌌다. uvicorn·라우터·미들웨어·설정 검증은 실제 코드 그대로다.
- 로그인 검증용 비밀번호·세션 시크릿은 스크립트 안에서 무작위로 만들어 127.0.0.1 스크래치 인스턴스에만 썼고, 파일·로그·이 기록 어디에도 값을 남기지 않았다(누출 검사는 "문자열이 있다/없다"만 출력).
- 기록의 종목은 데모 seed(`backend/seed/`)와 합성 티커(`AAA`·`BBB`·`CCC`)뿐이다.
- 리드에게 보내는 중간 체크포인트: 이 세션에는 SendMessage 도구가 없어(사용 가능한 도구는 Read·Grep·Glob·Bash·Write·handback뿐) 보내지 못했다. 대신 이 절에 항목마다 바로 적는다.

**진행 기록**
- 11:14 전체 `pytest` 1회차 시작 → 97% 부근에서 30분 넘게 멈춤. 리드 안내: 원인은 app-engineer가 11:12에 새로 만든 `backend/tests/test_static_serving.py`(작성 중, 1차 범위 밖). 11:46 **내가 띄운** pytest 프로세스 사슬만 종료하고(PID 31112와 그 부모 사슬, 시작 11:14:06, 로그 `A_pytest_full_hung_1114.log`) `--ignore=tests/test_static_serving.py`로 다시 돌렸다(11:46:36 시작, PID 33312 사슬). 같은 시각에 돌던 다른 팀원의 pytest(11:46:59 시작, `tests/test_static_serving.py` 단독)와 8001 개발 서버는 건드리지 않았다(종료 전후 `/api/health` 200).
- 11:50경 리드 정정: 멈춤은 app-engineer가 고쳤다고 함(테스트 도우미의 가짜 `receive()`가 매번 즉시 `http.request`를 돌려줘 Starlette `FileResponse`의 disconnect 대기와 무한 루프, "앱 코드 문제가 아님"이라는 주장). 이 주장은 내가 확인하지 않았고 **2차 반박 대상**이다(아래 "2차에서 볼 것").

### A. 재현 (백엔드 테스트·린트) — 통과

| 무엇 | 결과 | 시각·로그 |
| --- | --- | --- |
| `py -3.11 -m uv run pytest -o addopts="" -q -p no:cacheprovider --ignore=tests/test_static_serving.py` | **1436 passed**, 실패 0 (149.85초) | 11:46~11:49, `A_pytest_full2.log` |
| 보안·배포 테스트 5개 파일 한 번에 | **175 passed** | 11:53, `A_pytest_five.log` |
| 파일별 | `test_security` 71 / `test_auth` 31 / `test_demo_mode` 40 / `test_backup_db` 23 / `test_import_without_torch` 10 | 같은 로그 |
| `tests/test_static_serving.py` 단독(작성 중, 2차 대상) | 43 passed (4.7초) — 12:32의 파일(11:53 수정본) 기준 사실만 기록 | `A_pytest_static.log` |
| `ruff check . --no-cache` | All checks passed | `A_ruff.log` |
| `ruff format --check . --no-cache` | 191 files already formatted | 같은 로그 |

- 팀원 보고와 대조: risk-engineer 보고의 142(71+31+40)와 일치. 전체 수는 보고(1435 통과 + 1 실패)와 달리 **1436 통과**다. 알려진 실패 `test_portfolio_api.py::test_sparklines_read_closes_where_each_position_is_priced`는 이 시각의 작업 트리에서 통과했다(`test_portfolio_api.py` 26 passed; 수정 내용 자체는 app-engineer 영역이라 2차에서 본다).
- `.pytest_cache`·`.ruff_cache`를 저장소에 남기지 않으려고 `-p no:cacheprovider`·`--no-cache`를 붙였다. 결과에는 영향이 없다.
- **N-DEPLOY-1 (정보)** app-engineer 체크포인트는 `tests/test_import_without_torch.py`를 "11 passed"로 적었는데 지금 파일은 **10건**이다(`--collect-only`로 확인). 보고 이후 테스트가 줄었거나 보고가 틀렸다. 최종 보고에서 수를 맞출 것.

### B. 로그인 인스턴스 전수 (실제 uvicorn, 127.0.0.1:8011) — 통과 (110개 확인, 실패 0)

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_B_login.py` → `B_results.txt`, 서버 로그 `B_server.log`·`B2_server.log`. 12:16~12:17. 설정: `AM_ENV=development` + 무작위 비밀번호의 기본 비용 scrypt 해시 + 무작위 48바이트 시크릿, 스크래치 DB(alembic head + 합성 거래 3건).

- **라우트 열거**: `fastapi.routing.iter_route_contexts(app.routes)`로 실제 앱에서 67개(메서드×경로, 경로 61개)를 얻었다. 전부 `/api` 아래다(그 밖은 개발 모드의 `/docs`·`/redoc`·`/openapi.json`·`/docs/oauth2-redirect` 4개).
- **쿠키 없이 전 라우트**: 공개 4개(`GET /api/health`, `GET /api/auth/session`, `POST /api/auth/login`, `POST /api/auth/logout`)를 뺀 **63개 전부 401 `auth_required`**. 쓰기 라우트는 본문 없이/JSON 본문으로 두 번씩 보냈다. 통과한 라우트 없음.
- 보호 경로 57개 각각에 HEAD·OPTIONS·PATCH·PUT·DELETE·POST·TRACE를 보내도 전부 401.
- **경로 철자 28가지**(끝 슬래시, `//api/…`, `/api//…`, 대문자, `%2F`, `%61pi`, `/api/auth/../transactions`, `/api/auth/%2e%2e/…`, `/api/auth/..%2F…`, `/api/health/../…`, `;x`, `%00`, 절대 형식 `http://host/api/…` 등): 장부 데이터를 돌려준 것 없음. `/api/auth/` 접두어 아래 트릭은 전부 404(라우터 불일치), `/api/health` 쪽 트릭은 401, `/api/auth/session/`은 307 → 원래 경로.
- `X-Original-URL`·`X-Rewrite-URL`·`X-Forwarded-Prefix`·`X-Forwarded-For`·`Authorization`·`X-HTTP-Method-Override`·가짜 쿠키를 붙여도 401. `Host: evil.example` → 400.
- 쿠키 없는 전수 동안 DB 전 테이블 행 수 변화 없음, 시세 공급자 호출 0, 외부 서비스 대역 호출 0.
- **로그인**: 204 + `Set-Cookie: am_session=…; HttpOnly; Max-Age=604800; Path=/; SameSite=strict`(Domain 없음, 개발 모드라 Secure 없음), `Cache-Control: no-store`. 이후 `GET /api/auth/session`이 `authenticated: true`.
- **같은 요청이 쿠키로 열림**: GET 라우트 44개 중 401·403 없음(200 34개, 모델·학습 작업·투자자·강의가 없어서 404 9개, `news` 1개는 내 GDELT 대역이 던진 예외로 500 — 대역 탓).
- **쓰기 Origin 검사**: Origin 없음(비브라우저) 201, 같은 호스트 Origin 201. 다른 사이트 Origin 11가지(`http(s)://evil.example`, `null`, `http://127.0.0.1:8011.evil.example`, `http://evil.example@127.0.0.1:8011`, 다른 포트, 포트 없음, `localhost:8011`, `ftp://`, `//host`, 빈 값) 전부 **403 `csrf_origin_mismatch`**. Origin 없이 `Sec-Fetch-Site: cross-site`도 403. 전체 삭제(`DELETE /api/transactions?confirm=all`)와 로그아웃도 다른 사이트 Origin이면 403. 다른 사이트 Origin의 GET은 200이지만 `Access-Control-Allow-Origin`이 없어 페이지가 읽지 못한다.
  - 설계대로인 것(정보): 같은 호스트의 `https://` Origin은 통과(호스트만 비교), `AM_CORS_ORIGINS` 기본값의 `http://localhost:5173`은 신뢰 Origin이라 통과.
- **변조·만료 토큰 14가지**(MAC 한 글자, 만료만 늘림, nonce 변경, MAC 제거, 버전, 빈 값, 무작위, **올바른 키로 서명한 만료 토큰**, 다른 시크릿, 해시가 바뀐 뒤의 키, 256자 초과, 끝에 점, MAC 대문자화): 전부 401. production 쿠키 이름으로 보낸 유효 토큰도 개발 모드에서는 401.
- **로그아웃**: 204 + 쿠키 삭제(`Max-Age=0`). 같은 쿠키로 GET·POST 모두 401, 세션은 `authenticated: false`.
- **틀린 비밀번호 반복**: 1~5번째 401 `invalid_credentials`, **6번째부터 429 `rate_limited` + `Retry-After: 900`**. 잠긴 동안 맞는 비밀번호도 429(닫힘), `/api/health`는 200. 실패 응답에 쿠키 없음. 100KB 로그인 본문 → 413.
- **누출 검사**(로그인 성공 응답의 `Set-Cookie`를 뺀 모든 응답 본문·헤더 + 서버 로그 전체에서 문자열 검색): 비밀번호·틀린 비밀번호·해시·해시의 salt/key 부분·세션 시크릿·토큰·토큰 MAC **모두 없음**. 서버 로그의 로그인 관련 줄은 `login failed from 127.0.0.1` 꼴뿐이고 `scrypt$`·`password`·`Cookie`·`am_session` 문자열은 0회.
- **`AM_ENV=production` + 로그인**(같은 포트로 다시 띄움): 쿠키 없이 401 + HSTS·nosniff·X-Frame-Options·CSP·Referrer-Policy·`no-store`; `/docs`·`/redoc`·`/openapi.json` 404; 쿠키는 `__Host-am_session; HttpOnly; Max-Age=604800; Path=/; SameSite=strict; Secure`; 그 쿠키로 200, 같은 토큰을 개발용 이름으로 보내면 401; 다른 사이트 Origin 쓰기 403; 서버 로그에 비밀값 없음.
- 두 번 모두 끝난 뒤 8011 포트 닫힘 확인.

발견(둘 다 차단 아님):
- **N-DEPLOY-2 (정보)** 개발 모드(`AM_ENV=development`)에서 로그인을 켜도 `/docs`·`/redoc`·`/openapi.json`은 세션 없이 200이다(`/api` 밖이라 인증 미들웨어가 보지 않음, risk-engineer가 "알려진 한계"로 적은 것과 일치). DEPLOY.md는 "공개 데모를 돌리는 PC에서는 실제 앱(8001)에 로그인을 켠다"고 안내하는데 그 인스턴스가 바로 이 조합이다. 스키마는 공개 저장소 내용이라 데이터 노출은 아니다. 제안: DEPLOY.md "로그인" 절에 한 줄 적거나, 로그인이 설정되면 문서 경로도 닫는다.
- **N-DEPLOY-3 (정보)** 1,024자를 넘는 비밀번호를 보내면 422 응답의 `input`에 보낸 값이 그대로 돌아온다(FastAPI 기본 검증 오류, `B_results.txt` 8절). 보낸 사람에게만 가고 서버 로그에는 남지 않으며 실제 비밀번호는 1,024자 이하라 누출은 아니다. 제안: `LoginIn` 검증 오류에서 `input`을 빼면 깔끔하다.

### C. 데모 인스턴스 전수 (실제 uvicorn, 127.0.0.1:8013) — 통과 (72개 확인, 실패 0)

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_C_demo.py` → `C_results.txt`(1회차는 `C_results_run1.txt`), 서버 로그 `C_server.log`·`C2_server.log`. 12:24~12:27. 설정은 compose와 같게 `AM_ENV=production`·`AM_DEMO_MODE=true`·`AM_ALLOWED_HOSTS=["localhost","127.0.0.1","*.trycloudflare.com"]`·`AM_CORS_ORIGINS=[]`·`AM_CLIENT_IP_HEADER=CF-Connecting-IP`, 단 `AM_STATIC_DIR`은 주지 않았다(정적 서빙은 작성 중, 리드 지시). 합성 장부 `AAA`·`CCC`·`ETH-USD`.

- 1회차는 72개 중 5개가 FAIL이었는데 **전부 내 스크립트의 기대값 오류**였다(제품 문제 아님): ① 차단 20개와 허용 3개를 한 루프에서 돌려, 허용된 시뮬레이션이 채운 시세 캐시(`price_bars` 0→4,486)를 "쓰기 전수 뒤 변화"로 잡음 ② 없는 메서드 `FOO`는 uvicorn의 HTTP 파서가 앱에 닿기 전에 400으로 거절(닫힘) ③ 스크래치 uvicorn은 기본 `forwarded_allow_ips=127.0.0.1`이라 127.0.0.1에서 보낸 `X-Forwarded-For`를 믿음(컨테이너는 터널 주소만 믿는다 → F에서 확인). `patch_C.py`로 기대값을 고쳐 다시 돌린 결과가 아래다.
- **쓰기 라우트 23개 = 허용 3 + 차단 20**. 차단 20개를 본문 없이 / 유효한 JSON 본문 / `?confirm=all`로 세 번씩(60요청): **전부 403 `demo_read_only`**. 그 직후 DB 전 테이블 행 수 변화 없음, 시세 공급자 호출 0, 외부 서비스 대역 호출 0. multipart 업로드(`/api/imports/screenshot`)도 403.
- 허용 3개: `POST /api/auth/login` → 409 `login_not_configured`(쿠키 없음), `POST /api/auth/logout` → 204, `POST /api/projection/simulate` → 200. 시뮬레이션이 바꾼 테이블은 시세 캐시(`price_bars`·`symbol_syncs`)뿐이고 공급자에 물은 종목은 허용 집합 안이다.
- 경로 61개 전부에 POST·PUT·PATCH·DELETE·TRACE·PROPFIND(허용 3개 제외): 전부 403 `demo_read_only`. HEAD·OPTIONS는 전 경로 405(라우터).
- **우회 시도 38가지**: 끝 슬래시·`/api//…`·`%2F`·`%61pi`·`/api/projection/simulate/../transactions`·`simulate%2F..%2F..%2Ftransactions`·`/api/auth/login/../../transactions`·`;x`·`%20`·`%00`·절대 형식 → 403. `//api/…`·대문자 경로·`/%2Fapi/…`·`/./api/…`·`/x/../api/…` → 404(라우터 불일치, `/api`로 해석되지 않음). 소문자 메서드 `post` → 400(파서). `X-HTTP-Method-Override`·`X-HTTP-Method`·`X-Method-Override`·`_method=DELETE`·`X-Original-URL`·`X-Rewrite-URL`은 무시됨(GET은 GET으로, 허용된 POST는 그 경로로만 처리). chunked 본문 POST → 403. 한 연결에 `logout` 뒤 `DELETE 전체`를 이어 보내도 둘째는 403. 이 구간 전후 전 테이블 변화 없음, 거래 3건 그대로.
- 본문 상한: 허용 라우트에 70KB 본문 → 413, Content-Length 없는 80KB chunked → 413.
- **종목 가드**: 티커를 받는 GET 라우트 13개. 장부 밖 철자 — 경로형 9개 × 24가지(`BBB`, 소문자, 앞뒤 공백, `AAA,BBB`, `BBB,AAA`, `%2C`, `%00`, 전각 문자, `^GSPC`, `DOGE-USD`, `KRW-DOGE`, `..`, `KRW=X2`, 탭·개행·세미콜론 등) = 216요청, 쿼리형 4개 × 11가지 × 3형태(단독, 허용 종목 뒤에 반복, 앞에 반복) = 132요청 → **348요청 전부 403 `demo_symbol_not_allowed`**. 공급자 호출 기록에 허용 집합 밖 종목 0건, `price_bars`·`symbol_syncs`의 종목은 전부 허용 집합 안.
  - 혼합: `symbols=AAA,BBB`·`symbols=AAA&symbols=BBB`·공백/세미콜론/`|`/개행 구분 → 403. 허용 종목끼리 쉼표로 붙인 경로(`/api/market/AAA,SPY/history`) → 422(라우트의 티커 형식 검사, 공급자 호출 없음). 이름이 다른 파라미터(`Symbols=`, `symbols[]=`)는 가드도 라우트도 무시해 기본 목록으로 200. `start=1990-01-01`을 붙인 장부 밖 종목도 403. HEAD → 405.
  - 허용 종목 13가지 철자(`AAA`, `aaa`, 공백 포함, `eth`, `KRW-ETH`, `SPY`, `QQQ`, `btc`, `BRK-B`, `ARKK` 등)는 200.
- GET 라우트 44개 전수: 401 없음. 종목 캐시는 끝까지 허용 집합 안, 거래 3건 그대로.
- `/docs`·`/redoc`·`/openapi.json`·`/docs/oauth2-redirect` → 404. Host: `evil.example`·`127.0.0.1.evil.example`·`trycloudflare.com`(점 없는 최상위)·`abc.trycloudflare.com.evil.example`·빈 값 → 400, `abc.trycloudflare.com`·`localhost`·`LOCALHOST` → 200.
- 응답 헤더: 200·403(쓰기)·403(종목)·404(`/api` 안팎)·405·413·422 모두 HSTS(`max-age=31536000; includeSubDomains`)·`X-Content-Type-Options: nosniff`·`X-Frame-Options: DENY`·CSP(`default-src 'self'; script-src 'self'; … frame-ancestors 'none'`)·Referrer-Policy·COOP·Permissions-Policy가 붙고, `/api` 응답은 `Cache-Control: no-store`. 잘못된 Host의 400에는 헤더가 없다(TrustedHost가 가장 바깥, 알려진 한계). 다른 사이트 Origin의 preflight → 400, CORS 허용 헤더 없음.
- 요청 제한(같은 설정에 분당 30으로 다시 띄움): 연속 35회 → 200×30, 429×5. 429는 `rate_limited` + `Retry-After` + 보안 헤더. 거절된 쓰기도 같이 센다. `/api/health` 40회는 전부 200. 형식이 틀린 `CF-Connecting-IP`는 소켓 주소로 돌아가 계속 429.
- 끝난 뒤 8013 포트 닫힘 확인.

발견:
- **N-DEPLOY-4 (정보, 알려진 한계의 실측)** 데모에서 방문자의 평범한 GET이 내부 쓰기와 외부 호출을 일으킨다. GET 44개 전수 한 번에 `price_bars` +1,618행, `event_syncs` +2, `guru_syncs` +1, `upcoming_events` +5가 생겼고(`C_results.txt` 6절), 외부 대역 중 `congress.index`(하원 서기국 색인), `guru.fetch`(ARK/13F), `gdelt.daily`(뉴스)에 닿았다. 장부·규칙·정책·킬스위치·강의 진행 테이블은 변하지 않았다. risk-engineer·data-engineer 보고의 "알려진 한계"와 일치하고 DEPLOY.md "외부 호출"에도 적혀 있다. 실제 호출량은 F에서 컨테이너 로그로 다시 본다.
- **N-DEPLOY-5 (정보)** `AM_CLIENT_IP_HEADER=CF-Connecting-IP`인 인스턴스에 **직접** 붙으면 그 헤더 값만 바꿔 새 요청 한도를 받는다(`C_results.txt` 8절: 한도 소진 뒤 다른 값으로 200). 설정 설명대로 "모든 요청이 그 프록시를 거칠 때만 안전"하다. compose는 호스트의 127.0.0.1에만 포트를 열어 인터넷에서는 터널로만 닿으므로 지금 구성에서는 PC 안의 사용자만 할 수 있다. Cloudflare가 방문자가 보낸 같은 이름의 헤더를 덮어쓰는지는 터널을 띄우지 않아 **확인하지 못했다**(가설: 덮어쓴다).

### D. 시작 거부 — 통과 (99개 확인, 실패 0)

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_D_startup.py` → `D_results.txt`, 프로세스 출력 `D/*.log`. 12:29.

- **순수 함수 `deployment_problem`** 17조합: production 단독, 해시만(시크릿 없음, 개발·production 둘 다), 짧은 시크릿(16자), 형식이 틀린 해시, 평문을 해시 자리에 넣음, production의 약한 해시(n=16), 시크릿만 있고 해시·데모 없음 → 전부 거부. **데모 + 실매매 3조합(production/development/로그인 포함) → 전부 거부**(`AM_DEMO_MODE cannot be combined with real orders`). 이 조합은 지시대로 함수 호출로만 확인했다(실매매 값을 넣은 설정 객체를 만들지 않았고 서버도 띄우지 않았다). `config.py:188-194`에서 `real_orders_enabled=self.live_trading`으로 이 함수에 연결됨을 코드로 확인. production+데모, production+로그인, 개발 기본값은 허용.
- **설정 객체**(`Settings(_env_file=None, …)`) 8조합: 전부 `ValidationError`. `str()`·`repr()`에 넣은 해시·시크릿·표식 문자열 없음(`hide_input_in_errors`). 정상 조합의 `repr(settings)`에도 해시·시크릿이 없다(`SecretStr`).
- **실제 명령**(스크래치 DB, 127.0.0.1:8014): `python -m uvicorn app.main:app`과 엔트리포인트 첫 단계인 `python -m alembic upgrade head`를 6조합 × 2로 실행. 12번 모두 0이 아닌 종료 코드, 이유 문장 출력(`AM_ENV=production needs either AM_DEMO_MODE … or a login …`, `AM_AUTH_PASSWORD_HASH needs AM_SESSION_SECRET …`, `AM_SESSION_SECRET must be at least 32 bytes`, `AM_AUTH_PASSWORD_HASH: non-numeric scrypt cost …`, `… too cheap for production …`), 출력에 값 없음, pydantic의 `input_value` 없음. 스크래치 DB 파일은 만들어지지도 않았다(마이그레이션 전에 멈춤). 포트는 열리지 않았다.
- 이 12번의 프로세스는 `uvicorn app.main:app` 그대로라 앱이 스스로 `backend/.env`를 읽는다(내가 열어 본 것은 아니다). 시나리오가 `.env` 내용에 좌우되지 않게 `AM_DEMO_MODE=false`·`AM_AUTH_PASSWORD_HASH=`·`AM_SESSION_SECRET=`·스크래치 DB·`AM_MARKET_PROVIDER=fake`를 환경변수로 덮었다.

### E. 이미지 — 통과

빌드 시각의 작업 트리에는 app-engineer의 정적 서빙(`main.py` 끝 블록 + `api/frontend.py`)이 들어 있다. 12:38 이후 저장소에서 바뀐 것은 문서뿐이라(`find -newer`로 확인: `CLAUDE.md`·`README.md`·`docs/DEPLOY.md`·`docs/dev/*`) 아래 이미지는 2차의 "최종 트리" 이미지이기도 하다.

| 무엇 | 결과 | 근거 |
| --- | --- | --- |
| `docker build -t asset-manager-demo:verify .` | exit 0. 전 단계 CACHED(12:29에 다른 팀원이 같은 트리로 빌드해 둠) | `E_build.log` |
| `docker build --no-cache -t asset-manager-demo:verify-nocache .` | **exit 0, 28초**. `npm ci` 176개, `uv sync --locked --no-default-groups` 65개, `vite build` 통과 | `E_build_nocache.log` |
| 두 이미지의 `/app` 내용 | 파일 195개의 sha256 목록이 동일(`.pyc` 제외), `/opt/venv` 파일 수 11,136 동일 | 재현 가능한 빌드 |
| 크기 | **914MB** | `docker images` |
| 실행 사용자 | `Config.User=10001:10001`, 컨테이너 안 `id` → `uid=10001(app) gid=10001(app)` | `E_image_probe.txt` |
| `/app` 쓰기 | `/app`·`/app/app`·`/opt/venv` 쓰기 `PermissionError`(root 소유 0755), `/data`·`/tmp`만 가능. 엔트리포인트 0555 root | 같은 파일 |
| deploy/README "확인"의 find(사용자 10001과 root 둘 다) | 출력 없음 | — |
| 파일시스템 전체에서 `.env*`·`*.db`·`*.sqlite*`·`artifacts`·`.git`·`*.key`·`*.joblib`·`*.pt` | 없음. `*.pem`은 CA 인증서 묶음, `*.log`는 기반 이미지의 apt/dpkg 로그뿐 | — |
| `/app`·`/data`의 `tests`·`test_*`·`conftest.py`·`docs`·`.git*`·`.claude`·`*.md` | 없음. `/app` 최상위는 `alembic`·`alembic.ini`·`app`·`scripts`·`seed`·`static` | — |
| 설치된 것 | 배포판 65개. `torch`·`transformers`·`tokenizers`·`lightgbm`·`pytest`·`ruff`·`pip`(venv) **없음**. `sklearn`·`yfinance`·`curl_cffi`·`pypdf`·`anthropic`·`uvicorn`은 기본 의존성으로 있음 | `E_image_probe.txt` |
| 환경변수(이미지) | `AM_ENV=production`·`AM_STATIC_DIR`·`AM_DATABASE_URL`·`AM_ARTIFACTS_DIR` + 파이썬 기반 이미지의 값뿐. Labels 없음 | `docker inspect` |
| `docker history --no-trunc` | 26줄. `secret·token·passw·hash·api key·credential·메일 주소·TUNNEL·ANTHROPIC·FINNHUB·SEC_USER` 패턴 0건. `AM_*=`는 위 4개뿐 | `E_history.txt` |
| compose 없이 `docker run --rm asset-manager-demo:verify` | **종료 코드 1**, `AM_ENV=production needs either AM_DEMO_MODE (read-only demo) or a login …`, `input_value` 없음 | `E_bare_run.log` |
| 빌드 컨텍스트(README의 명령) | 파일 **299개**: `backend/{alembic,alembic.ini,app,pyproject.toml,scripts,seed,uv.lock}` + `frontend/{src,public,설정 파일}`. `.env`·`*.db`·`artifacts/`·`tests/`·`docs/`·`deploy/`·`.git`·`node_modules`·`dist` 없음. **git이 무시하는 파일 0개**(`git check-ignore`) | `E_context_files.txt` |
| `static/index.html` | 796바이트, inline `<script>` 0개 | `E_image_probe.txt` |

- data-engineer 보고의 "컨텍스트 285개"는 그 뒤 추가된 파일(보안 모듈·프론트 테스트 등) 때문에 299개가 됐다. 구성은 허용 목록 그대로다.
- 정보: 이미지에 `backend/scripts/`가 통째로 들어가 `backup_db.py`·`check_lesson_links.py`도 실린다(비밀 아님, 실행 경로에서 쓰지 않음). `/opt/venv/.gitignore`는 uv가 만든 가상환경 표식이다.
- compose가 빌드한 `asset-manager-demo:local`도 `/app` 해시가 `:verify`와 같다(F는 그 이미지로 실행).

### F. 컨테이너 데모 실행 (터널 없이, 127.0.0.1:8012) — 통과 (1회차 78개 중 2개 FAIL은 내 스크립트 탓, 재확인 통과)

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_F_container.py` → `F_results.txt`, 로그 `F_up.log`·`F_demo_first_start.log`·`F_demo_run.log`·`F_demo_restart.log`·`F_down.log`. 12:45~12:46. compose 호출은 전부 `docker compose -f deploy/docker-compose.yml --env-file <스크래치>/F_compose.env -p am-verify …`이고 env 파일은 `COMPOSE_PROFILES=`(빈 값)·`DEMO_LOCAL_PORT=8012` 두 줄이다. `deploy/.env`는 만들지 않았다. `config --services`가 `demo` 하나만 내는 것을 확인한 뒤 `up -d --build demo`로 서비스 이름까지 지정했다(cloudflared 컨테이너는 한 번도 생기지 않았다: `docker ps -a` 라벨 필터 결과 `demo asset-manager-demo:local running` 한 줄).

- **첫 시작**: `up`이 돌아온 뒤 **10초 만에 healthy**(전체 13초, 같은 날 두 번째 실행은 17초). 로그: `alembic upgrade head`(마이그레이션 18단계) → `demo ledger is empty: python -m seed.load` → 거래 16줄 → `demo ledger seeded` → `starting uvicorn (1 worker)`. fake 공급자 경고 없음. seed 직후 DB: `transactions` **16**, `price_bars` 4,043, `symbol_syncs` 9, 나머지 0. 장부 종목은 seed의 9개(AAPL·MSFT·VOO·NVDA·TSLA + 코인 4종).
  - DEPLOY.md의 "첫 시작은 시세를 받아 1~3분"은 이 PC에서 13~17초였다(상한으로는 맞다).
- **쓰기**: 차단 20개 → 403 `demo_read_only`. 끝 슬래시·`/api//…`·`%2F`·`simulate/../transactions`·`login/../../transactions` → 403. `DELETE /api/transactions?confirm=all` → 403. GET에 `X-HTTP-Method-Override: DELETE` → 무시(거래 16건 그대로 나열). 로그인 → 409 `login_not_configured`, 로그아웃 → 204.
- **종목 가드**: 티커 라우트 13개에 `IBM`·`DOGE-USD`·`ZZZZQ`(단독, `AAPL`과 혼합) → 전부 403 `demo_symbol_not_allowed`.
- **1회차의 FAIL 2개**("거절된 요청 뒤 DB 변화 없음", "캐시 종목 변화 없음": `price_bars` 4,043→4,546, `symbol_syncs` 9→10)는 내 스크립트가 그 구간에 **허용된 읽기** `GET /api/transactions`(메서드 오버라이드 확인용)를 섞어 보냈기 때문이다. 그 읽기가 원화 환산용 환율 시계열 한 종목(허용 집합의 `KRW=X`, 503봉)을 채웠다. 거절 요청만 보낸 재확인(2차 R1, `R_results.txt`): **115개 거절 요청 전후 DB의 모든 테이블 행 수와 캐시 종목 목록이 동일**. 끝까지 캐시 종목은 허용 집합 안이었다(`IBM`·`DOGE` 없음).
- **핵심 읽기 한 바퀴**(20개): 전부 응답. `holdings` 0.4초, `history` 1.3초, `learn/skills` 1.3초, `projection/assumptions` 5.6초(첫 시세 수집), 예측은 404 `not_trained`(모델 없음, 의도), LSTM은 501 `lstm_not_installed`. `POST /api/projection/simulate` 200(0.5초), 방문자가 요청할 수 있는 최대 크기(40년 × 20,000경로)도 0.8초. 70KB 본문 → 413. 이 읽기들로 바뀐 테이블은 시세 캐시뿐(`price_bars` 4,043→14,079).
  - 외부 호출을 아끼려고 컨테이너에서는 의회 거래(`/api/congress/*`)·투자자 비교(`/api/gurus*`)를 **부르지 않았다**(C에서 대역으로 확인). 뉴스는 2차 R4에서 한 번만 불렀다.
- **문서·Host·헤더**: `/openapi.json` → 404(JSON). `/docs`·`/redoc` → **200 `text/html` 796바이트**(정적 서빙이 들어온 뒤로는 SPA의 `index.html`이 답한다. Swagger·스키마는 나오지 않는다 → N-DEPLOY-7). Host `evil.example`·`host.docker.internal`·`demo` → 400, `abc.trycloudflare.com`·`localhost`·`127.0.0.1` → 200. 200·403(쓰기)·403(종목)·404·`GET /` 모두 HSTS·nosniff·`X-Frame-Options: DENY`·CSP·Referrer-Policy·COOP·Permissions-Policy, `/api`는 `no-store`, **`Server` 헤더 없음**. 없는 `/api` 경로는 JSON 404.
- **요청 제한(기본 분당 120)**: 헤더 없이 연속 135회(0.8초) → **200×121, 429×14, 첫 429는 122번째**. 429는 `rate_limited` + `Retry-After: 1` + 보안 헤더 + `no-store`. 서로 다른 `X-Forwarded-For` 12개·`X-Real-IP`/`Forwarded` 12개 → 전부 429(uvicorn은 터널 주소 `172.30.35.3,172.30.35.4`의 전달 헤더만 믿고, 이 PC에서 온 요청의 상대 주소는 게이트웨이 `172.30.35.1`). 형식이 틀린 `CF-Connecting-IP` → 429. 거절된 쓰기도 429. `/api/health` 20회·정적 페이지는 제한 없음. 다른 `CF-Connecting-IP` 값은 새 한도(N-DEPLOY-5와 같음).
- **`docker inspect`**: Mounts = named volume `am-verify_demo-data` → `/data` **하나**(Binds도 그것뿐, 호스트 경로 없음). Tmpfs = `/tmp: rw,noexec,nosuid,nodev,size=128m,mode=1777`. PortBindings = `8000/tcp → 127.0.0.1:8012`뿐. `ReadonlyRootfs=true`, `CapDrop=["ALL"]`·CapAdd 없음, `no-new-privileges:true`, `User=10001:10001`, Privileged false, 메모리 1GiB·pids 512·CPU 1.5, restart `unless-stopped`, 네트워크 `am-verify_edge` 172.30.35.2, ExtraHosts 없음. 환경변수 이름 25개에 PASSWORD·SECRET·TOKEN·API_KEY 류 없음, `AM_LIVE_TRADING=false`·`AM_DEMO_MODE=true`·`AM_ENV=production`·`AM_MARKET_PROVIDER=yfinance`·`AM_SEC_USER_AGENT` 빈 값.
- **컨테이너 안**: uid/gid 10001, `CapEff=0`·`CapBnd=0`, `NoNewPrivs=1`, seccomp 필터, 루트 파일시스템 `ro`, `/tmp`는 `noexec`. `/app`·`/app/app`·`/app/static`·`/opt/venv`·`/`·`/etc`·`/home` 쓰기 → 전부 `Read-only file system`, `/tmp`·`/data`만 가능. 프로세스는 uvicorn 1개(`--workers 1`).
- **위험 확인(사실)**: 컨테이너 안에서 `host.docker.internal`이 `192.168.65.254`로 풀리고, `GET http://host.docker.internal:8001/api/health`(Host를 `localhost:8001`로 준 urllib 요청 한 번, 읽기 전용) → **200 `{"status":"ok"}`**. DEPLOY.md "공개 데모를 돌리는 PC에서 지킬 것"의 경고는 사실이다. Host를 맞춰 주면 실제 앱의 `TrustedHost`도 통과한다(D-035의 "브라우저 전제라 방어가 아니다"와 일치).
- **로그**: 423줄, Traceback 0, 500 응답 0, ERROR 0.
- **재시작**: 7초 만에 healthy, `demo ledger has 16 transactions: seed skipped`, seed는 두 번의 시작 동안 한 번만 실행, 거래 16건 유지.
- **정리**: `down -v` 뒤 프로젝트의 컨테이너·볼륨·네트워크 없음, 8012 닫힘.
- **네트워크 없는 첫 시작**(`docker run --network none`, 새 볼륨, compose와 같은 잠금 옵션·환경, `DEMO_SEED_RETRY_DELAY=5`; 2차 R6에서 실행, `R_nonet_abort.log`·`R_nonet_continue.log`):
  - 기본(`abort`): **종료 코드 1**(9초). `ERROR: seeding the demo ledger failed (output above).` → `Not serving an empty demo and not falling back to synthetic prices.` → `Exiting in 5s; the restart policy then tries again …`. 원인은 `MarketDataError: yfinance request failed for AAPL: … Could not resolve host`(파이썬 traceback이 로그에 찍힌다). uvicorn은 뜨지 않았고 fake 전환 없음. 남은 DB는 `transactions` 0·`price_bars` 0(합성 값이 쓰이지 않았다).
  - `DEMO_SEED_ON_FAILURE=continue`: `serving with an EMPTY ledger` 문구와 함께 뜬다. `/api/transactions`·`/api/portfolio/holdings` → `[]`, `/api/portfolio/summary`·`/api/market/SPY/quote` → **502**(`yfinance request failed …`), 지어낸 가격 없음.
- 미실시: 터널을 거친 요청(Cloudflare의 `CF-Connecting-IP`, 방문자별 한도), cloudflared 컨테이너의 `read_only` 동작, 브라우저로 화면 열기(확장 연결 없음).

발견:
- **N-DEPLOY-6 (보통 — 코드 결함은 아니고 공개 전 사용자 단계)** 지금 이 PC의 실제 앱(8001)은 로그인이 꺼져 있고(`GET http://127.0.0.1:8001/api/auth/session` → `auth_required: false`, 12:5x에 호스트에서 한 번 조회) 데모 컨테이너에서 닿는다(위 "위험 확인"). 이 상태로 터널을 열면, 데모 앱이 뚫릴 경우 실제 장부를 읽고 고칠 수 있다. DEPLOY.md·TODO_FOR_ME가 이미 "공개 전 8001에 로그인을 켠다"를 사용자 단계로 적고 있다. **터널을 열기 전에 반드시 끝나 있어야 하는 조건**으로 표시한다.
- **N-DEPLOY-7 (정보)** production + 정적 서빙에서 `/docs`·`/redoc`은 404가 아니라 200(SPA의 `index.html`)이다. API 스키마·Swagger는 나오지 않고 `/openapi.json`은 404라서 DEPLOY.md의 "API 문서 꺼짐"은 기능상 맞다. 응답 코드로 "꺼짐"을 점검하는 사람은 `/openapi.json`을 봐야 한다(CI 스모크는 그렇게 한다).
- **N-DEPLOY-8 (정보, 배포 범위 밖의 기존 동작)** 네트워크가 없을 때 `/api/market/fx/usdkrw`·`/api/market/kimchi`는 502가 아니라 404 `Unknown symbol 'KRW=X'`로 답한다(`R_results.txt` R6). 합성 값은 아니지만 "연결 실패"가 "없는 종목"으로 표시된다.

### G. 백업 — 통과 (34개 확인, 실패 0)

재현: `py -3.11 <스크래치>/run_G_backup.py` → `G_results.txt`(1회차 `G_results_run1.txt`). 12:57~12:59. **모든 호출에 `--source`/`-Source`와 스크래치 대상 폴더를 명시**했다(기본 원본은 앱의 실제 DB라서 기본값으로는 한 번도 실행하지 않았다). 기본 대상 `%USERPROFILE%\asset-manager-backups`는 이 검증으로 생기지 않았다.

- 1회차의 FAIL 3개는 내 테스트가 사본을 `mode=ro`(immutable 아님)로 열어 사본 옆에 `-wal`/`-shm`을 만들고, 그 파일을 다음 확인에서 센 탓이다. 내 쪽 열기를 `immutable=1`로 바꿔 다시 돌렸다(`patch_G.py`).
- `backup_db.py`: 생성(이름 `asset_manager-YYYYMMDD-HHMMSS.db`) → 사본 `integrity_check` = `ok`, 5,000행 전부. 원본 파일은 sha256 동일. 대상 폴더에 `.partial` 없음.
- **서버가 켜진 상황**: 다른 연결이 WAL에 250행을 커밋하고 연 채로 있는 동안 백업 → 사본에 5,250행(`-wal`에만 있던 행 포함). 백업 뒤 그 연결의 쓰기도 정상.
- **보관 개수**: `--keep 3`으로 5번 → 최신 3개만 남고 오래된 것 삭제, 삭제 목록 출력. 이름이 정확히 맞지 않는 파일 7종(`….db.bak`, `….db.partial`, `other.db`, 날짜 형식이 다른 것, 대문자 이름, 메모 파일)은 그대로.
- **실패 시 삭제 없음**(`--keep 1`을 줘도): 없는 원본 → exit 1(원본을 새로 만들지 않음), DB가 아닌 파일 → exit 1, 페이지를 훼손한 DB → exit 1(사본도 남지 않음), `--keep 0` → 거부, 대상이 파일 → 실패, 메모리 DB URL·비 sqlite URL → 거부. 매번 대상 폴더의 파일 해시가 그대로였다. `sqlite:///` URL을 `--source`로 주는 경로 동작. 같은 초에 두 번 실행하면 둘째는 `not overwriting`으로 exit 1(덮어쓰지 않음).
- **`scripts/backup-db.ps1`**(PowerShell, `-Source`·`-DestDir` 명시): ASCII 전용 확인, 백업 생성·exit 0, `-Keep 2`로 3번 → 2개, 상대 `-DestDir`은 호출한 폴더 기준(`backend/` 아래에 아무것도 생기지 않음), 없는 원본 → 종료 코드 1·삭제 없음, `-Keep 0`은 파라미터 검사에서 거부, 공백·한글이 든 대상 경로 동작.
- 미실시: 실제 DB에 대한 실행(금지), 작업 스케줄러 등록(`schtasks`, 사용자 단계).

발견:
- **N-DEPLOY-9 (정보)** 원본을 연 프로세스가 없을 때 백업을 돌리면 **원본 옆에 `<원본>-shm`(32,768바이트)·`<원본>-wal`(0바이트)이 생겨 남는다**(`G_results.txt` 6행). WAL 모드 DB를 읽기 전용으로 열 때 SQLite가 만드는 파일이고 장부 행은 들어 있지 않으며 `.gitignore`가 `*.db-wal`·`*.db-shm`을 무시한다. 원본 `.db` 자체는 바이트 단위로 같다. `backup_db.py` 머리말의 "The source … is never created or modified"는 "원본 파일은 바뀌지 않지만 SQLite의 보조 파일이 옆에 생길 수 있다"가 정확하다. 사본도 WAL 모드라 다른 도구로 열면 같은 보조 파일이 생긴다. 제안: 머리말 한 줄 보완.

### H. 비밀·규칙 누출 — 통과 (자세한 표는 2차 T)

2차 범위까지 들어온 최종 작업 트리로 한 번에 확인했다(`run_T_leaks.py` → `T_results.txt`). 1차 질문에 대한 답만 적는다.

- 커밋될 파일(수정 45 + 신규 41)에 scrypt 해시 문자열 0건, 토큰·키 0건(걸린 1건은 테스트의 가짜 값), 실제 메일 주소 0건, 계좌 형식 숫자 0건, `AM_LIVE_TRADING`을 켜는 줄 0건. 테스트의 해시는 실행할 때 `hash_password()`로 만드는 값이고 비밀번호·시크릿 상수는 `test-only …`로 시작하는 테스트 문자열이다(`tests/test_auth.py:47-49`, `tests/test_demo_mode.py:64-65`).
- `deploy/.env`·`backend/.env`·`*.db`·`*.db-wal`/`-shm`·`*.db.partial`·`frontend/dist`·`backend/artifacts/`·`.claude`·`backend/.dev-backend*.log`는 `git check-ignore`로 무시됨을 확인했고, 추적 중인 파일에도 신규 파일에도 그런 것이 없다.
- 실행 경로의 Fake: `FakeProvider`는 `deps.get_provider`에서 `AM_MARKET_PROVIDER == "fake"`일 때만 만들어진다(`backend/app/deps.py:48-49`). compose는 `yfinance`로 고정, Dockerfile에는 그 변수가 없고, 엔트리포인트는 `fake`이면 경고만 찍는다(`entrypoint.sh:35-37`). seed 실패·시세 실패 때 Fake로 넘어가는 코드는 없다(F의 네트워크 없는 시작 두 가지로 실측).
- `AM_LIVE_TRADING`: 저장소 전체에서 이 값을 **쓰는** 곳은 없다. 읽는 곳은 `config.py`(검증), `services/rules.py`(표시), `strategy/execution.py:156`(`settings.live_trading is True`일 때만 live 경로)뿐이고, compose와 CI는 `false`로 명시한다. 이 검증 중에도 켜지 않았다.

### I. 문서 대조 — 통과 (자세한 대조는 2차 S)

`docs/DEPLOY.md`(리드가 13시 전후 고친 현재 파일)와 `deploy/README.md`의 명령·기본값·서비스 이름·응답 코드는 실제와 맞다. 차이는 정보 수준 둘뿐이다: `/docs`의 응답 코드(N-DEPLOY-7), 첫 시작 소요 시간(문서 1~3분, 실측 13~17초). 항목별 대조는 2차 S에 적는다.

### 1차 요약

| 항목 | 판정 | 확인 수 | 비고 |
| --- | --- | --- | --- |
| A 재현 | 통과 | pytest 1436(정적 서빙 제외)·ruff 2종 | 2차 J에서 1479로 다시 확인 |
| B 로그인 인스턴스 | 통과 | 110 | 비로그인 63개 라우트 전부 401 |
| C 데모 인스턴스 | 통과 | 72 | 쓰기 20개 403, 종목 348요청 403 |
| D 시작 거부 | 통과 | 99 | 실제 명령 12회 모두 거부, 값 노출 없음 |
| E 이미지 | 통과 | — | 914MB, 비루트, 비밀·DB·모델·테스트 없음 |
| F 컨테이너 | 통과 | 78 + 재확인 | 공개 전 전제 N-DEPLOY-6 |
| G 백업 | 통과 | 34 | 스크래치 DB만 |
| H 누출 | 통과 | 86개 파일 | — |
| I 문서 | 통과 | — | 정보 수준 차이 2 |

1차 발견: N-DEPLOY-1~9. **중대 0, 보통 1(N-DEPLOY-6: 코드가 아니라 공개 전 사용자 단계), 나머지 정보.** 1차 범위에서 커밋을 막는 것은 없다.

1차 미실시: 터널을 거친 요청 전부(금지), 브라우저 확인(확장 연결 없음), `hash_password` 대화형 실행(에이전트는 비밀번호를 입력하지 않음 — 테스트로 갈음), 실제 DB 백업(금지), 컨테이너에서의 의회·투자자 라우트(외부 호출 절약), 리드에게 보내는 중간 메시지(SendMessage 도구 없음 — 이 파일로 대신).

## 배포 1단계 검증 2차 (2026-11-11, verifier)

대상: app-engineer의 최종 보고(13:00경) 이후의 작업 트리 — 정적 서빙(`backend/app/api/frontend.py` + `main.py` 끝 블록), torch 없는 경로, 로그인 화면·데모 UI, conftest 환경 고정, ISSUE-051, CI. 규칙과 전제는 1차와 같다(코드·설정·문서 수정 없음, 터널 없음, `backend/.env`·실제 DB 미접근, 스크래치 인스턴스는 `.env`를 읽지 않게 하고 외부 서비스는 기록용 대역). 1차 E·F의 이미지는 12:38에 빌드했고 그 뒤 저장소에서 바뀐 것은 문서뿐이라(`find -newer`) 그 이미지가 곧 최종 트리의 이미지다.

진행 기록: 13:50경 세션이 끊겼다 다시 이어졌다. 그 전까지의 실행 결과는 스크래치 결과 파일에서 수치를 옮겨 적었고 통과한 실행은 다시 돌리지 않았다.

### J. 재현 — 통과

재현: `sh <스크래치>/run_J.sh` → `J_backend.log`·`J_frontend.log`·`J_genapi.log`. 12:53~12:57.

| 무엇 | 결과 | 주장과 대조 |
| --- | --- | --- |
| `py -3.11 -m uv run pytest -o addopts="" -q -p no:cacheprovider`(전체, 정적 서빙 포함) | **1479 passed** (160.5초) | app-engineer 주장 1479와 일치 |
| `ruff check . --no-cache` / `ruff format --check . --no-cache` | All checks passed / 191 files already formatted | 일치 |
| `tests/test_import_without_torch.py` 수집 | **10건** | 체크포인트 1의 "11 passed"는 틀렸고 최종 보고도 "verifier 10, agent 11"로만 적었다 → N-DEPLOY-1 유지(수는 10이 맞다) |
| `tests/test_static_serving.py` 수집 | 43건 | 일치 |
| `npm test` | **45 files, 309 tests passed** (6.0초) | 일치 |
| `npm run lint`(oxlint) | 출력 없이 종료 0 | 일치 |
| `npm run build`(`tsc -b && vite build`) | 통과, `dist/assets` 25개 파일 | 일치 |
| `npm run gen:api` 전후 sha256 | `openapi.json` `748715f7…`, `schema.d.ts` `10105e14…` — **전후 동일** | "diff 없음" 일치 |

- `gen:api`는 추적 중인 두 파일을 다시 쓰는 명령이라, 실행 전에 바이트 사본을 떠 두고 결과가 다르면 원본을 되돌리게 해 두었다. 결과가 같아 되돌릴 일은 없었다(`J_genapi.log`: `GENAPI: no difference`).
- "시계 +200일에서도 1479 passed"는 N에서 따로 본다(그 주장 자체는 맞지만 충분하지 않았다 → N-DEPLOY-10).
- "Chrome으로 데모 컨테이너 확인(CSP 위반 없음)"은 브라우저를 쓸 수 없어 **재현하지 못했다**. 대신 K에서 번들과 CSP를 정적으로 대조했다.

### K. 정적 서빙 — 통과 (컨테이너와 로컬 uvicorn 둘 다, 실패 0)

같은 점검 묶음(`static_checks.py`)을 두 곳에 돌렸다.
- **컨테이너**(리눅스, compose와 같은 설정, 127.0.0.1:8012): `run_R_container.py` → `R_results.txt` R3절. 12:57~12:58.
- **로컬 uvicorn**(Windows, `AM_ENV=production`·`AM_DEMO_MODE=true`·`AM_STATIC_DIR=frontend/dist`, 127.0.0.1:8015): `run_KL_local.py` → `KL_results.txt`(54개 확인, 실패 0), 서버 로그 `K_server.log`. 13:03.

| 확인 | 컨테이너 | 로컬 uvicorn |
| --- | --- | --- |
| `GET /` → 200 `text/html`, `Cache-Control: no-cache` | 통과(796바이트) | 통과, `frontend/dist/index.html`과 바이트 동일 |
| 페이지 경로 12개(`/coach`, `/assets/AAPL`, `/assets/BRK.B`, `/assets/BTC-USD`, `/learn/abc`, `/login?next=/coach`, `/assets/AAA?symbol=ZZZ`, `/assets/ZZZZ?symbols=IBM,KO`, `/transactions/`, `/a/b/c/d`, `/docs`, `/redoc`) → `index.html` + `no-cache` | 통과 | 통과 |
| `index.html`이 가리키는 해시 파일(`/assets/index-*.js`·`.css`) → 200, `text/javascript`/`text/css`, `public, max-age=31536000, immutable`, Content-Length = 본문 길이, nosniff + CSP | 통과 | 통과. dist의 **28개 파일 전부** 바이트 동일하게 서빙, `.js` 25개 전부 `text/javascript`, `.css`는 `text/css`(Windows 레지스트리의 형식이 아니라 모듈의 표를 쓴다) |
| `/theme-init.js`·`/favicon.svg`·`/index.html` → 200 + `no-cache` | 통과 | 통과 |
| 빌드 확장자인데 없는 경로 8개(`.js`·`.css`·`.map`·`.woff2`·`.json`·`.png`·`sw.js`·`.webmanifest`) → 404, `index.html` 아님 | 통과 | 통과 |
| 없는 `/api` 경로(`/api/nothing`, `/api`, `/api/`, `/api/transactions/x/y`, `/api/assets/AAPL`) × GET·HEAD·POST·PUT·DELETE → HTML 없음, 200 없음 | 통과: GET·HEAD 404, **POST·PUT·DELETE는 403 `demo_read_only`**(데모) | 같음. GET은 `{"detail":"Not Found"}` |
| 페이지·파일 경로로의 POST·PUT·DELETE·PATCH → 404 | 통과 | 통과 |
| **경로 탈출 74가지** → 폴더 밖 바이트 0 | 통과: 200(`index.html` 그대로) 67, 404 6, 400 1 | 통과: 200(`index.html`) 68, 404 5, 400 1 |
| 데모 종목 가드가 페이지 경로를 막지 않음(`/assets/AAA?symbol=ZZZ` → 200 `index.html`), API 가드는 그대로(`/api/market/ZZZ/quote` → 403) | 통과 | 통과 |
| 정적 요청은 요청 제한에 세지 않음 | 한 주소에서 180회 → 전부 200 | L에서 확인 |
| 정적 요청이 외부 서비스·시세 공급자에 닿지 않음 | — | 대역 호출 0 |

- 경로 탈출 목록: `..`, `%2e%2e`, `%2f`, 이중 인코딩(`%252e`), 백슬래시와 `%5c`, `//etc/passwd`, `/C:/Windows/win.ini`·`/C:Windows/win.ini`, UNC, `file://`, 점 파일(`/.env`, `/.git/config`, `/assets/.env`), `/app/app/config.py`, `/data/demo.db`, `/proc/self/environ`, NUL(`%00`), `....//`, `..;/`, 과장 UTF-8(`%c0%ae`), `../` 60번, 4KB 경로, 70,000자 경로, Windows의 `::$DATA`·끝 점·끝 공백·대문자 이름·장치 이름(`CON`, `NUL`, `aux.js`), 저장소의 `backend/.env`·`backend/asset_manager.db`·`backend/app/config.py`·`src/main.tsx`·`package.json`을 향한 상대 경로. 판정 기준: 200 응답의 본문이 `index.html`과 바이트 동일하지 않거나, 어떤 응답이든 `root:x:`·`class Settings`·`SQLite format 3`·`AM_ENV=` 같은 표식이 있으면 누출. **두 환경 모두 0건.**
- 코드로 본 이유(`api/frontend.py:97-112`): 조각 중 점으로 시작하는 것이 있으면 거절, 그 뒤 `resolve()`한 경로가 폴더 안의 일반 파일일 때만 서빙. 포함 검사는 정규화 뒤에 하므로 백슬래시·드라이브 문자·심볼릭 링크가 폴더 밖을 가리켜도 걸린다.

**"멈춤은 테스트 도우미 탓이고 실제 서버에서는 일어나지 않는다"는 주장 — 반박 실패(주장 유지).** 실제 서버 두 곳에 다음을 보냈고 모두 끝났다.
- 한 연결(keep-alive)에서 HEAD·GET을 섞어 35요청: 컨테이너 0.06초, 로컬 0.05초. HEAD는 본문 없이 전체 Content-Length.
- Range 9종(380,719바이트 번들): `bytes=0-99` → 206·100바이트, `100-`·끝 10바이트·`-50` → 206, 범위 초과 → 416, 다중 범위 → 206, 형식 오류 3종 → 400. 전부 응답.
- 동시 50요청(번들·페이지·API·정적 혼합): 전부 200·전체 길이, 컨테이너 0.09초, 로컬 0.07초.
- 본문 전송 중 RST로 끊기 30회 + 응답을 읽지 않고 끊는 HEAD 20회 + 요청을 다 보내지 않고 끊기 20회 + 읽지 않고 붙어만 있는 연결 20개. 그 직후 `/api/health`·`/`·번들·`/api/health` → 전부 200, 각 0.02초 이내.
- 끝난 뒤 유휴 상태: 컨테이너 `docker stats` **CPU 0.12%**(pids 27, 메모리 322MiB/1GiB)·healthy, 로컬은 유휴 4초 동안 서버 프로세스 **CPU 시간 0.00초**. 서버 로그에 Traceback·500 없음(양쪽).
- 따라서 FileResponse의 disconnect 대기가 실제 서버에서 바쁜 루프가 된다는 증거는 찾지 못했다. (테스트 도우미를 고쳤다는 부분은 `tests/test_static_serving.py` 43건이 4.7초에 끝나는 것으로만 확인했다.)

**시작 거부**: `AM_STATIC_DIR`이 빈 폴더 / 없는 폴더 / 파일일 때 세 번 모두 종료 코드 1, `RuntimeError: AM_STATIC_DIR=… has no index.html. Build the frontend …`. 빈 값이면 기존 동작(1차 C: `GET /` 404, 정적 블록 미설치).

**빌드 산출물과 CSP**: `dist/index.html`(796바이트)에 inline `<script>` 0, inline 이벤트 핸들러(`on…=`) 0, 외부 출처 `src`/`href` 0. 번들 25개 파일에서 `eval(`·`new Function(`·`new Worker(`·`new WebSocket(`·`importScripts(`·`document.write(` 0건, `fetch("http…` 0건. 번들 안의 절대 URL은 `www.w3.org`(SVG·XHTML 네임스페이스 20), 라이브러리 문서 링크(reactrouter.com, react.dev, redux.js.org, github.com, bit.ly, tradingview.com)와 `localhost` 2건뿐이고 요청 대상이 아니다(문자열·오류 메시지). CSS에 `@import`·외부 `url()` 없음. `script-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'`과 충돌하는 것을 찾지 못했다. **브라우저 콘솔에서의 CSP 위반 0은 재현하지 못했다(미실시).**

발견:
- **N-DEPLOY-12 (정보)** app-engineer 보고의 "`/api` unknown path → JSON 404 for any method (also in demo)"는 데모에서는 정확하지 않다: 쓰기 메서드는 라우터에 닿기 전에 읽기 전용 계층이 **403 `demo_read_only`**(JSON)로 답한다. HTML이 나오지 않는다는 요점은 맞고 더 닫힌 쪽이다. 보고·문서의 표현만 고치면 된다.
- 정보(번호 없음): Windows에서는 `assets\.env`처럼 백슬래시로 이은 조각이 "점으로 시작하는 조각" 규칙을 지나친다. 그래도 폴더 포함 검사는 그대로라 dist 안의 파일만 나올 수 있고, dist에는 점 파일이 없다(확인). 배포 대상은 리눅스 컨테이너다.

### L. 로그인 + 정적 서빙 (실제 uvicorn, `AM_ENV=production`, 스크래치 DB, `frontend/dist`) — 통과

`KL_results.txt` L절, 서버 로그 `L_server.log`. 설정: 무작위 비밀번호의 기본 비용 해시 + 무작위 시크릿, `AM_RATE_LIMIT_PER_MINUTE=8`, `AM_CORS_ORIGINS=[]`.

- 세션 없이: `/`·`/login`·`/login?next=/coach`·`/coach`·`/assets/AAPL`·`/theme-init.js`·`/favicon.svg`·해시 파일 3개를 4번씩 **40요청 전부 200**(분당 8 제한에도 429 없음 → 정적은 제한에 세지 않는다). 페이지에 CSP·HSTS·X-Frame-Options·nosniff.
- 세션 없이: `/api/portfolio/summary` → **401 `auth_required`**, 없는 `/api` 경로 → 401(HTML 아님), `/api/auth/session` → `{auth_required: true, authenticated: false, demo_mode: false}`.
- 로그인 → 204 + `__Host-am_session` 쿠키 → `/api/portfolio/summary` 200, 없는 `/api` 경로는 JSON 404 → 로그아웃 204 → 같은 쿠키 거절.
- `/api` 한도는 그대로 동작(연속 12회 중 429 발생)하고 그동안에도 페이지·파일은 200.
- 서버 로그에 비밀번호·시크릿·해시·토큰 없음. 끝난 뒤 8015 닫힘.
- 미실시: 실제 브라우저에서의 로그인 흐름(`Secure` 쿠키는 https에서만 저장되므로 터널 뒤에서만 볼 수 있다), 401 뒤 `/login?next=…` 이동, 모바일 헤더. 프론트 단위 테스트(`Login.test.tsx`·`App.test.tsx`·`queryClient.test.ts`)가 통과한다는 것만 J에서 확인했다.

### M. conftest의 환경 고정 — 통과

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_M_conftest.py` → `M_results.txt`.

- `tests/conftest.py:10-22`가 app을 import하기 전에 `os.environ`에 `AM_ENV=development`·`AM_DEMO_MODE=false`·`AM_AUTH_PASSWORD_HASH=`·`AM_SESSION_SECRET=`·`AM_RATE_LIMIT_PER_MINUTE=0`·`AM_CLIENT_IP_HEADER=`·`AM_STATIC_DIR=`·`AM_ALLOWED_HOSTS=[기본값]`을 넣는다(환경변수가 `.env`보다 우선).
- 적대적 셸 환경(`AM_ENV=production`, `AM_DEMO_MODE=true`, 테스트용 무작위 해시·시크릿, `AM_RATE_LIMIT_PER_MINUTE=1`, `AM_CLIENT_IP_HEADER=CF-Connecting-IP`, `AM_STATIC_DIR=frontend/dist`, `AM_ALLOWED_HOSTS=["only.example"]`)을 준 채 API 테스트 10개 파일(`test_portfolio_api`·`test_coach_api`·`test_learn_api`·`test_static_serving`·`test_imports`·`test_imports_manual`·`test_corporate_actions`·`test_rules_api`·`test_market_data`·`test_forecasts_api`)을 돌렸다: **평범한 환경 275 passed, 적대적 환경 275 passed**. 401·403·429·400으로 무너지는 테스트 없음. (`tests/test_transactions*.py`라는 파일은 없다. 거래 API는 위 파일들과 `test_ledger.py`가 다룬다.)
- `backend/.env`는 건드리지 않았다(셸 환경변수로만 흉내 냈다).

**`AM_LIVE_TRADING`은 고정되지 않는다 — 영향 확인(코드):**
- 그 값을 읽어 동작이 갈리는 곳은 `app/strategy/execution.py:156`(`live = settings.live_trading is True`) 하나다. live이면 `live_factory()`를 부르는데 기본값이 `live_broker_unavailable`(같은 파일 122행)이고 `NotImplementedError`를 던져 결과가 `failed`/"실매매 브로커가 없음"이 된다. **저장소에 실제 주문을 내는 브로커 구현이 없다**(`place_order`·`submit_order`·증권사 API 이름으로 검색해 0건). 그래서 개발자의 `.env`가 실매매 값을 켜 두었더라도(변수 `AM_LIVE_TRADING`에 참 값) 테스트가 실주문 경로에 닿을 수는 없다.
- 남는 영향은 표시값을 단언하는 테스트(`rules`·`coach` 응답의 `live_trading: false`)가 깨질 수 있다는 것뿐이다.
- 배경 작업이 실제 DB에 쓰는 경로도 봤다: 동기화·학습 라우트를 부르는 테스트(`test_congress_api`·`test_gurus_api`·`test_demo_mode`)는 전부 `get_session_factory`를 테스트 DB로 바꾼다.

발견:
- **N-DEPLOY-11 (정보)** conftest가 `AM_LIVE_TRADING`을 고정하지 않는다. 지금은 실주문 구현이 없어 위험이 아니지만, 실매매 브로커를 붙이는 날에는 "테스트는 항상 false"가 conftest에 있어야 한다. 제안: 같은 `os.environ.update`에 `"AM_LIVE_TRADING": "false"` 한 줄(브로커 구현보다 먼저).

### N. ISSUE-051과 날짜 의존 — 수정은 통과, 같은 종류의 테스트가 더 있다 (N-DEPLOY-10, 수정 대기)

**ISSUE-051 수정이 테스트를 약하게 만들었나 — 아니다.** `git diff tests/test_portfolio_api.py`: 스파크라인 테스트만 `get_portfolio_service`를 `PortfolioService(db, market, today=lambda: TODAY)`로 바꿔 끼우고, 기대값을 `TODAY` 기준 30일 창의 공급자 종가로 계산한다. 단언은 `AAPL`(달러 종가)·`KRW-BTC`(원화 종가) 시계열의 **값 일치**와 봉 수 **`(23, 31)`**(이전에는 `0 < len(aapl) < len(btc)`)이다. "평일 < 매일"과 원화 시계열을 여전히 단언하고 오히려 더 좁다. 그 대가로 이 테스트는 라우트의 기본 시계 배선을 지나지 않는다(다른 포트폴리오 테스트가 기본 배선을 쓴다).

**시계를 옮겨 본 결과.** app-engineer의 플러그인(`scratchpad/shift_clock.py`: 서비스 클래스의 **기본 인자** 시계 9개만 옮김)과, 그 한계를 메운 내 플러그인(`verifier/deploy/shift_clock2.py`: 함수 본문에서 `date.today()`·`datetime.now()`를 부르는 모듈 `api/market`·`services/forecasts`·`services/predictions`·`services/projection`·`services/corporate_actions`의 `date`/`datetime` 이름까지 교체) 두 가지로 전체 pytest를 돌렸다. 로그 `N_shift.log`·`N_shift2.log`·`N_bisect.log`.

| 이동 | app-engineer 플러그인 | 내 플러그인(본문 시계 포함) |
| --- | --- | --- |
| +45일 | 1479 passed | **1 failed**: `tests/test_ml.py::test_train_smoke_and_prediction_api` (`ValueError: Need 30 rows after warm-up, have 10`) |
| +400일 | **1 failed**: `tests/test_rules_api.py::test_check_reports_each_holding_in_its_own_currency` (`assert c["bars"] > 0` → 0) | 2 failed (위 둘) |
| +1200일 | — | 12 failed (위 둘 + `tests/test_forecasts_api.py` 10건) |

단일 테스트로 경계를 좁힌 결과(오늘 = 2026-11-11):

| 테스트 | 통과하는 마지막 이동 | 처음 실패 | **실제 달력으로** | 원인 |
| --- | --- | --- | --- | --- |
| `test_ml.py::test_train_smoke_and_prediction_api` | +19일 | +20일 | **2026-12-01부터 실패**(11-30까지 통과) | `services/predictions.py:86` `_history_start()`가 실제 `date.today()`에서 112일((30+40)×1.6)을 거슬러 간다. 테스트의 `FakeProvider(today=TODAY)`는 2026-10-16에서 끝나므로 창에 남는 봉이 매일 줄어 30행 아래로 떨어진다 |
| `test_rules_api.py::test_check_reports_each_holding_in_its_own_currency` | +365일 | +380일 | **2027-11-21경부터** | `services/rules.py:60` `BARS_LOOKBACK = timedelta(days=400)`. 오늘−400일이 2026-10-16을 넘으면 봉 0개 |
| `test_forecasts_api.py`(16건 중 10건) | +680일 | +720일 | 2028-09-21 ~ 2028-10-31 사이 | 예측 서비스의 730일 창 |
| `test_projection.py`·`test_market_data.py`·`test_demo_mode.py` | +1500일 | +1900일(4건) | 2030-12 ~ 2032-01 사이 | 5년 창·기본 365일 창 |

- 첫 줄이 급하다: **지금 코드 그대로면 약 3주 뒤(2026-12-01)부터 `backend` CI 잡과 로컬 `pytest`가 코드 변경 없이 빨갛게 된다**(CI는 `lstm` 그룹을 설치해 `tests/test_ml.py`를 돌린다). ISSUE-051과 같은 종류(고정된 가짜 시세 + 실제 시계)다.
- app-engineer 보고의 "+0·+200에서 1479 passed"와 "본문에서 `date.today()`를 부르는 곳은 `services/forecasts.py`·`services/projection.py`·`api/market.py`"는 그 자체로는 맞지만, **`services/predictions.py:86`(가장 먼저 깨지는 곳)과 `services/rules.py`의 400일 창이 빠져 있고** +200일까지만 봐서 +400일의 실패를 놓쳤다.
- 내 플러그인의 한계: 시스템 시계를 실제로 바꾼 것이 아니라 모듈 안의 `date`·`datetime` 이름을 하위 클래스로 바꾼 것이다. +0일에서는 전부 통과하고, 실패마다 원인 줄과 메시지가 직접 대응하므로(위 표) 대역이 만든 가짜 실패일 가능성은 낮다고 본다. 날짜는 단일 테스트 재실행으로 좁힌 값이다(+19 통과, +20 실패).

발견:
- **N-DEPLOY-10 (보통, 커밋 전 수정 대상 — 리드 지시로 app-engineer가 수정 중)** 실제 날짜에 따라 깨지는 테스트가 ISSUE-051 말고 4묶음 더 있다(위 표). 제안: 스파크라인과 같은 방식으로 테스트가 서비스의 시계를 `TODAY`에 고정하거나, 본문의 `date.today()`를 주입 가능한 시계로 바꾼다. 그리고 "시계 이동 +N일" 점검을 +400일 이상까지 CI 밖의 정기 점검으로 남긴다. **수정 뒤 재확인(`shift_clock2`로 +0/+20/+60/+400일)은 리드의 완료 알림을 기다리는 중이다.**

### O. torch 없는 경로 — 통과

- **데모 컨테이너 안**(`R_results.txt` R4): `GET /api/predictions`·`/api/predictions/AAPL`·`/AAPL/backtest`·`/AAPL/train` → 전부 **501 `lstm_not_installed`**. `POST /api/predictions/AAPL/train`은 데모에서는 읽기 전용 계층이 먼저 403 `demo_read_only`. 장부 밖 티커는 403 `demo_symbol_not_allowed`.
- **같은 이미지의 로그인 인스턴스**(쓰기가 데모 잠금에 걸리지 않게; `run_O_image_login.py` → `O_results.txt`, 10개 확인 실패 0, 14:10): 쿠키 없이 401 → 로그인 → **5개 라우트(POST 포함) 전부 501 `lstm_not_installed`**. 페이지는 세션 없이 200, 장부는 빈 목록(데모가 아니면 seed가 돌지 않는다), 컨테이너 로그에 비밀값 없음. 시세는 `fake`, DB는 tmpfs, 끝나고 컨테이너 삭제.
- **이미지 안에서 `import app.main`**: 성공. 설치된 것 중 `torch`·`transformers`·`lightgbm`·`tokenizers` 없음, import 뒤 `sys.modules`에도 없음. `app.ml`·`app.ml.sentiment`(torch를 쓰지 않는 부분)만 올라온다.
- **뉴스**: 데모 컨테이너에서 `GET /api/news/AAPL` 한 번 → 200(10.9초), `sentiment_enabled: false`, `finnhub_enabled` 키 있음, 감성 점수가 든 기사 0. 다만 **기사 자체가 0건**이었고 응답의 `warnings` 내용을 기록하지 않아 이유(GDELT 응답 없음·제한 등)는 확인하지 못했다. "가짜 점수 없음"은 코드로도 확인: `deps.get_scorer`가 `finbert_installed()`가 아니면 `None`을 돌려주고 대체 채점기는 없다(`backend/app/deps.py:160-165`). 외부 호출을 아끼려고 다시 부르지 않았다.
- `tests/test_import_without_torch.py` 10건 통과(J).

### P. CI — 통과 (GitHub Actions 자체는 미실시)

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_P_ci.py` → `P_results.txt`(10개 확인, 실패 0), 스모크 출력 `P_smoke_am-verify-ci.log`. 13:17.

- `ci.yml`은 YAML로 읽힌다. 트리거: `push`의 `branches: [main, agent-team]` + `pull_request`. 잡 3개(`backend`·`frontend`·`docker`), 같은 ref의 새 실행이 이전 실행을 취소.
- `backend` 잡: `uv sync --locked --no-group ml` → ruff 2종 → `alembic upgrade head`·`alembic check` → `uv run pytest` → OpenAPI diff. 로컬에서 `py -3.11 -m uv sync --locked --no-group ml --dry-run`: 잠금 파일 그대로 풀리고 **빠지는 것은 `ml` 그룹(lightgbm·transformers와 그 의존성)뿐, torch(`lstm`)는 남는다**. `pyproject.toml`의 `default-groups = ["dev", "ml", "lstm"]`와 맞다. 따라서 CI는 `tests/test_ml.py`를 돌린다(→ N-DEPLOY-10의 첫 줄이 CI에 그대로 해당).
- `docker` 잡을 ci.yml에 적힌 스크립트 그대로 재현했다. 바꾼 것은 이미지 태그(`:ci` → 같은 트리의 `:verify`), 컨테이너 이름, 호스트 포트(8000은 이 PC의 다른 프로젝트가 써서 8016)뿐이고, 스모크 단계는 `jq`가 이 PC에 없어 데모 컨테이너의 네트워크를 공유하는 alpine 도우미 안에서 **수정 없이**(`BASE=http://127.0.0.1:8000`) 실행했다.
  - "The image has no secrets, database or trained models in it" → exit 0.
  - "Start the demo container"(잠금 옵션 + `AM_MARKET_PROVIDER=fake`) → 기동, 엔트리포인트가 `WARNING: AM_MARKET_PROVIDER=fake serves synthetic prices. Never publish this instance.`를 찍는다.
  - "Smoke test" → **exit 0, `::error::` 0줄**.
  - **대조 실행**: 같은 이미지를 데모 잠금 없이(`AM_ENV=development`·`AM_DEMO_MODE=false`) 띄우면 같은 스모크가 `session.demo_mode is not true`로 **exit 1**. 스모크가 잠금이 빠진 것을 잡는다.
  - 끝나고 컨테이너 2개 삭제, 포트 닫힘.
- `AM_MARKET_PROVIDER=fake`가 있는 곳: `ci.yml`의 스모크 기동 줄 하나(주석으로 CI 전용임을 적음). `deploy/docker-compose.yml`은 `yfinance`로 고정, `Dockerfile`에는 그 변수가 없고, `entrypoint.sh`는 값이 `fake`이면 경고만 한다. 실행 경로에 fake 전환 없음.
- 미실시: 실제 GitHub Actions 실행(푸시하지 않음), ubuntu 러너에서의 `setup-uv`·`setup-node` 동작.

### Q. 화면 문구·규칙 — 통과 (코드 대조, 브라우저 미실시)

- **금지어**: `frontend/src` 전체에서 `추천|사세요|파세요|오를|예상 수익`이 걸리는 파일은 11개이고 전부 이번 변경 이전의 문구·테스트다(`lib/coach.ts`·`lib/forecast.ts`·`lib/learn.ts`의 규칙 문구, 접기 안의 "오를 확률", 금지어를 단언하는 테스트들). 이번에 새로 생긴 `lib/auth.ts`·`lib/session.tsx`·`pages/Login.tsx`·`api/errors.ts`·`api/queryClient.ts`와 `App.tsx`에는 0건. `lib/auth.test.ts:88`이 `AUTH_TEXT`의 모든 문장에 같은 식을 단언한다. `ForecastPanel.tsx`의 이번 변경은 버튼 비활성 3줄뿐이다(`git diff`).
- **문구 단일 출처**: 로그인·데모 문장은 전부 `lib/auth.ts`의 `AUTH_TEXT`에 있고, 서버의 403 문장 "데모에서는 저장·수정할 수 없어요"(`security/demo.py`)와 `AUTH_TEXT.demoReadOnly`가 글자까지 같다.
- **데모 띠는 데모에서만**: `App.tsx:126-131` `{session?.demo_mode && …}`. 빌드된 번들에 띠 문장이 들어 있다(`dist/assets/index-*.js` 1곳).
- **데모에서 쓰기 버튼 비활성**: `useDemoMode()` 사용처가 보고의 12개 화면·컴포넌트와 일치한다 — `TransactionForm`·`Transactions`·`BulkDelete`·`CorporateActions`·`Import`(2곳)·`Rules`·`Coach`(2곳)·`Lesson`·`Compare`·`CongressTrades`·`ForecastPanel`·`AssetDetail`. 여기에 띠용 `App.tsx`.
- **색**: 새 파일(`Login.tsx`·`App.tsx`·`session.tsx`·`auth.ts`)에 16진수 색·`rgb()`·Tailwind 색상 숫자 클래스·inline `style` 없음. 띠는 `bg-ink`·`text-surface`(CSS 변수 토큰)이고 손익 색을 쓰지 않는다.
- **로그인 뒤 이동**: `nextPath()`는 `/`로 시작하고 `//`·백슬래시가 없는 앱 내부 경로만 받고, 값은 React Router `navigate()`로만 쓰인다(다른 사이트로 보내지 못한다).
- 서버가 최종 판단자라는 점: 버튼 비활성과 무관하게 데모의 쓰기는 서버가 403으로 막는다(C·F·R).
- 미실시: 실제 화면에서의 띠·버튼 상태·모바일 헤더(브라우저 없음). app-engineer가 남긴 것으로 적은 3건(데모 예측 영역의 안내 문장 없음, 가져오기 파일 선택은 막지 않음, `useForecastTraining` 폴링이 `Retry-After`를 따르지 않음)은 화면 완성도 문제이고 서버 방어와 무관하다.

### R. 최종 이미지·컨테이너 — 통과 (48개 확인, 실패 0; 단 N-DEPLOY-10 수정 뒤 이미지가 달라지면 스모크 재확인 필요)

재현: `cd backend; py -3.11 -m uv run python <스크래치>/run_R_container.py` → `R_results.txt`, 로그 `R_demo.log`·`R_nonet_abort.log`·`R_nonet_continue.log`. 12:57~12:58. 이미지는 1차 E의 것(12:38 빌드, 그때의 트리 = app-engineer 최종 보고 시점의 코드).

- R1 거절 요청만 115개 → 전부 403, **전후 DB 완전 동일**(F의 1회차 FAIL 해명).
- R2 **seed가 실제 시세를 썼다는 증거**: seed된 16개 단가를 같은 종목·같은 날의 `FakeProvider` 값과 비교 → 일치 0건(예: 2026-01-15 VOO 636.62 대 합성 236.93, 같은 날 원화 BTC 1.409억 대 합성 5.32억).
- R3 정적 서빙(K의 컨테이너 열), R4 torch 없는 경로(O).
- 컨테이너 로그 643줄에 Traceback 0·500 0·ERROR 0. 경고는 70,000자 경로에 대한 `Invalid HTTP request received.` 한 줄.
- R5 `down -v` 뒤 잔여물 없음. R6 네트워크 없는 시작(1차 F에 적음).
- 1차 F의 `docker inspect`·컨테이너 내부 확인·`host.docker.internal:8001` 도달은 같은 이미지·같은 compose라 다시 돌리지 않았다.
- **주의**: 14시 전후로 app-engineer가 N-DEPLOY-10 때문에 `backend/app/services/predictions.py`를 고치고 있다(작업 트리에서 수정 시각 13:54 확인). 그 파일은 이미지에 들어가므로 **수정이 끝나면 이미지를 다시 빌드해 CI 스모크(P)와 LSTM 501(O)을 한 번 더 확인해야 "최종 트리 이미지"라는 말이 다시 성립한다.** 실제 시세 seed를 다시 할 필요는 없다(바뀌는 것이 LSTM 서비스의 시계뿐이라면).

### S. 문서 대조 — 통과 (정보 수준 차이만)

대상: 지금의 `docs/DEPLOY.md`(165줄, 리드가 N-DEPLOY-2를 "로그인" 절에 반영한 판)와 `deploy/README.md`.

| 문서의 말 | 실제 | 근거 |
| --- | --- | --- |
| 장부는 `backend/seed/`의 데모 거래, 실제 보유 내역은 이미지에도 볼륨에도 없다 | 맞음: seed 16건, 이미지·컨텍스트에 DB 없음 | E, F |
| 시세는 실제 시세, 못 받아도 합성으로 바꾸지 않는다 | 맞음 | R2, F(네트워크 없는 시작) |
| `/api` 쓰기는 모두 403 `demo_read_only`, 계산만 하는 요청만 허용 | 맞음: 차단 20, 허용 3(`simulate`·로그인·로그아웃) | C, F, R1 |
| 다른 티커는 403 `demo_symbol_not_allowed` | 맞음 | C, F, R1 |
| 방문자 주소당 분당 120회 | 맞음(121번째까지 통과, 기본값 `DEMO_RATE_LIMIT_PER_MINUTE:-120`). "방문자 주소당"은 터널 뒤에서만 성립하는데 그건 미실시 | F |
| 예측 모델 없음으로 답한다 | 맞음: `forecasts/status`가 `trained: false`, 종목 예측 404 `not_trained` | F |
| `/docs`·`/openapi.json` 꺼짐 | 기능상 맞음. `/openapi.json` 404, `/docs`는 200(SPA 껍데기) | N-DEPLOY-7 |
| 데모와 실매매를 함께 켜면 시작 거부 | 맞음(순수 함수로만 확인) | D |
| `Copy-Item .env.example .env` → `COMPOSE_PROFILES=` → `docker compose up -d --build` → `ps`에서 healthy | 같은 compose 파일을 `--env-file`로 돌려 확인(`deploy/.env`는 만들지 않음). 기본 포트 8010(`DEMO_LOCAL_PORT:-8010`) | F |
| 첫 시작 1~3분 | 이 PC에서 13~17초 | F, R1 |
| seed를 못 받으면 빈 데모를 띄우지 않고 약 5분 뒤 다시 시도 | 맞음: 기본 `DEMO_SEED_RETRY_DELAY` 300초 뒤 종료 코드 1, `restart: unless-stopped`(지연은 5초로 줄여 실측) | F |
| "화면 위에 데모 안내 띠", "데모에서는 저장·수정할 수 없어요" | 코드·번들·서버 응답 문장으로만 확인. **브라우저로는 보지 못했다** | Q |
| quick/named 터널 절차(`logs tunnel`, `TUNNEL_TOKEN`, `DEMO_HOSTNAME`, 서비스 `http://demo:8000`, `--profile quick down` 뒤 `up -d`) | 서비스 이름 `tunnel`·`tunnel-named`, 변수 이름, 앱 포트 8000, `DEMO_HOSTNAME`이 `AM_ALLOWED_HOSTS` 셋째 항목이 되는 것은 compose 파일과 일치. **실행은 하지 않았다(금지)** | compose 파일 |
| 백업 기본 대상 `%USERPROFILE%\asset-manager-backups`, 최근 14개, `-DestDir`·`-Keep`, 서버가 켜져 있어도 된다 | 맞음(스크래치 DB로) | G |
| 컨테이너는 이 PC의 localhost 서비스에 닿을 수 있다 → 8001에 로그인을 켠다 | 사실 | F, N-DEPLOY-6 |
| `py -3.11 -m uv run python -m app.security.hash_password`(두 번 묻고 한 줄 출력) | 모듈·동작은 코드와 테스트로 확인. 대화형 실행은 하지 않았다(에이전트는 비밀번호를 입력하지 않는다) | `security/hash_password.py` |
| `.env.example`에 시크릿 만드는 명령이 있다 | 맞음(`backend/.env.example:49`) | — |
| 로그인 안 한 `/api`는 401, production은 데모나 로그인 없이는 시작 거부 | 맞음 | B, D |
| 5번 틀리면 15분 잠금, 로그인 7일 유지, 해시·시크릿을 바꾸면 전부 로그아웃 | 맞음: 6번째 429 + `Retry-After: 900`, `Max-Age=604800`, 다른 시크릿·다른 해시로 서명한 토큰 401 | B |
| 개발 실행에서는 로그인을 켜도 `/docs`가 열려 있다 | 맞음 | B |
| 프로세스 1개 | 맞음(`--workers 1`, 컨테이너 프로세스 1개) | F |
| (README) `127.0.0.1:8010`만 연다 / "확인" 절의 `Invoke-RestMethod`·`curl.exe … -X POST`·`find`·`docker inspect` | 응답 코드와 출력이 문서대로(403, 출력 없음, volume 하나·Tmpfs `/tmp`·HostIp 127.0.0.1) | E, F |
| (README) 빌드 컨텍스트 목록 명령(PowerShell here-string) | **적힌 그대로 PowerShell에서 실행**: exit 0, 299개 파일, `.env`·`.db`·`artifacts/`·`tests/` 0건(`S_readme_context.log`) | — |
| (README) 실패 안내 문구(`AM_ENV=production needs either AM_DEMO_MODE …`, seed 실패 설명, `DEMO_SEED_ON_FAILURE=continue`, `400 Invalid host header`) | 메시지·동작 일치. `Pool overlaps`/`DEMO_SUBNET_PREFIX`는 겹침을 만들지 않아 미실시 | D, E, F |

발견:
- **N-DEPLOY-13 (정보)** README "확인" 절의 두 명령에 작은 빈틈이 있다. ① `find /app /data /tmp /root /home …`은 컨테이너 사용자 10001로 돌아 `/root`를 읽지 못하고 `2>/dev/null`이 그걸 가린다(내가 `--user 0`으로 다시 돌려 `/root`에도 없음을 확인). 제안: 명령에 `--user 0`. ② 빌드 컨텍스트 명령은 실행할 때마다 태그 없는 이미지를 하나 남긴다(내 것은 지웠다). 제안: `-t`를 붙이고 끝에 `docker rmi`, 또는 한 줄 안내.

### T. 누출 최종 확인 — 통과

재현: `py -3.11 <스크래치>/run_T_leaks.py` → `T_results.txt`. `git status --short --untracked-files=all`의 수정 45개(diff의 추가 줄만)와 신규 41개(전체), 합쳐 86개 파일 7,499줄.

| 검사 | 걸린 것 | 해석 |
| --- | --- | --- |
| scrypt 해시 문자열 | 0 | 테스트는 실행 중 `hash_password()`로 만든다 |
| 메일 주소 | 6(`backend/tests/test_backup_db.py`의 `user@db.example`) | 메일이 아니라 "sqlite가 아닌 URL은 거부"를 보는 가짜 `postgresql://user@db.example/…`의 일부 |
| 토큰·키 접두어(JWT, `sk-ant-`, `ghp_`, `AKIA`, `xox*`) | 1(`backend/tests/test_security.py:541`) | `fake_key = "sk-ant-api03-FAKE-0123456789"` — 시작 오류가 값을 찍지 않는지 보는 테스트의 **가짜 값**(이름에 FAKE, 길이 28) |
| 비밀 변수에 값 대입 | 2(`docs/dev/VERIFICATION.md:1538-1539`) | 내가 1차 D에 옮겨 적은 **오류 문장**(`AM_AUTH_PASSWORD_HASH needs AM_SESSION_SECRET …`, `AM_AUTH_PASSWORD_HASH: non-numeric scrypt cost …`)이다. 변수 이름과 메시지뿐이고 값은 없다 |
| `AM_LIVE_TRADING`을 켜는 줄 | 0 | — |
| 40자 이상 불투명 문자열 | 0(생성 파일·잠금 파일 제외) | — |
| 계좌 형식 숫자 | 0 | — |
| 공인 IPv4 | 2(`test_security.py:417, 423`의 `1.1.1.1`, `6.6.6.6`) | 클라이언트 주소 헤더 테스트의 예시 주소 |
| 사용자 프로필 경로(일반명 `user` 외) | 0 | — |

- 추적 중인 파일 가운데 `.env`·`*.db*`·`*.sqlite*`·`dist/`·`*.log`·`.claude/`·`backend/artifacts/`·`node_modules/` → **0**. 신규(무시되지 않은) 파일 가운데 그런 것 → **0**. `git check-ignore`가 `deploy/.env`·`backend/.env`·`backend/asset_manager.db`·`frontend/dist/…`·`.claude/…`·`backend/artifacts/…`·`backend/.dev-backend.log`·`*.db.partial`·`*.db-wal`을 모두 무시로 답한다.
- **실제 보유 정보**: 바뀐 문서·배포 파일에 나오는 대문자 토큰 가운데 티커로 읽히는 것은 합성(`AAA`·`BBB`·`CCC`), 벤치마크(`ARKK`·`BRK`·`SPY`·`QQQ`), 테스트 철자(`DOGE-USD`·`ETH-USD`·`GSPC`)뿐이다. 이 기록(F·R)에 내가 적은 종목과 가격은 공개 저장소의 `backend/seed/load.py`에 있는 데모 9종목과 그 거래일의 시장 종가다. **실제 장부와 대조하지는 못했다**(열 수 없으므로) — 실제 보유 종목이 우연히 이 목록과 겹치는지는 사용자만 판단할 수 있다.
- 이 검사 뒤에 바뀐 파일(app-engineer의 N-DEPLOY-10 수정, 이 기록의 추가분)은 handback 직전에 같은 스크립트로 한 번 더 본다.

### 2차 요약 (N-DEPLOY-10 수정 재확인 전의 상태)

| 항목 | 판정 | 확인 수 | 비고 |
| --- | --- | --- | --- |
| J 재현 | 통과 | pytest 1479, vitest 309, lint·build·gen:api | 주장과 일치(테스트 수 10/11만 정정) |
| K 정적 서빙 | 통과 | 컨테이너 + 로컬(54) | 멈춤 주장 반박 실패, 경로 탈출 0건 |
| L 로그인 + 정적 | 통과 | L절 14 | 브라우저 미실시 |
| M conftest 고정 | 통과 | 275 × 2 | `AM_LIVE_TRADING` 미고정은 정보(N-DEPLOY-11) |
| N 날짜 의존 | **발견 있음** | — | ISSUE-051 수정은 통과. N-DEPLOY-10 수정 대기 |
| O torch 없는 경로 | 통과 | 10 + R4 | 뉴스 0건의 이유는 미확인 |
| P CI | 통과 | 10 | GitHub Actions 자체는 미실시 |
| Q 문구·규칙 | 통과 | 코드 대조 | 브라우저 미실시 |
| R 최종 이미지·컨테이너 | 통과 | 48 | predictions.py 수정 뒤 재빌드 스모크 필요 |
| S 문서 | 통과 | 표 24행 | 정보 2 |
| T 누출 | 통과 | 86개 파일 | handback 전 재실행 예정 |

**발견 전체(1·2차)**

| 번호 | 심각도 | 한 줄 | 언제까지 |
| --- | --- | --- | --- |
| N-DEPLOY-1 | 정보 | `test_import_without_torch.py`는 10건(보고의 11은 오기) | 보고·기록 정정 |
| N-DEPLOY-2 | 정보 | 개발 모드 + 로그인에서 `/docs` 등은 세션 없이 열림 | DEPLOY.md에 반영됨(확인) |
| N-DEPLOY-3 | 정보 | 1,024자 초과 비밀번호의 422가 입력을 되돌려 줌 | 뒤로 |
| N-DEPLOY-4 | 정보 | 데모의 GET이 내부 쓰기·외부 호출(하원·ARK·GDELT)을 일으킴 | 알려진 한계, 뒤로 |
| N-DEPLOY-5 | 정보 | 직접 연결에서는 `CF-Connecting-IP` 값으로 한도를 새로 받음 | 터널 뒤 확인(사용자) |
| N-DEPLOY-6 | **보통** | 지금 8001은 로그인 없음 + 컨테이너에서 닿음 | **터널을 열기 전**(사용자 단계) |
| N-DEPLOY-7 | 정보 | production의 `/docs`는 200(SPA 껍데기), 스키마는 안 나옴 | 뒤로 |
| N-DEPLOY-8 | 정보 | 네트워크 없을 때 환율 조회가 502가 아니라 404 | 뒤로(배포 범위 밖) |
| N-DEPLOY-9 | 정보 | 백업이 원본 옆에 `-shm`·`-wal`을 남김 | 머리말 보완, 뒤로 |
| N-DEPLOY-10 | **보통** | 날짜 의존 테스트 4묶음, 첫 번째는 **2026-12-01부터 실패** | **커밋 전**(수정 중) |
| N-DEPLOY-11 | 정보 | conftest가 `AM_LIVE_TRADING`을 고정하지 않음(실주문 구현 없음) | 실매매 브로커 전 |
| N-DEPLOY-12 | 정보 | 데모에서 없는 `/api` 경로의 쓰기는 404가 아니라 403(JSON) | 보고 표현 정정 |
| N-DEPLOY-13 | 정보 | README "확인" 명령 2개의 빈틈(`/root` 미포함, 태그 없는 이미지) | 뒤로 |

중대 0. **커밋 전에 끝나야 하는 것은 N-DEPLOY-10 하나**(수정 → 재확인). **터널을 열기 전에 끝나야 하는 것은 N-DEPLOY-6**과 아래 미실시 가운데 터널 항목이다.

**미실시와 이유**
- 터널(quick·named) 기동과 그 뒤의 모든 확인: Cloudflare가 넣는 `CF-Connecting-IP`와 방문자별 한도, https에서의 `Secure`·`__Host-` 쿠키 저장, cloudflared의 `read_only` 동작, 공개 주소의 Host 허용 — **금지 사항이라 하지 않았다. 공개 직후 사용자가 README "확인" 절과 함께 볼 것.**
- 브라우저로 보는 것 전부(데모 띠, 버튼 비활성, CSP 콘솔, 로그인 화면 흐름, 모바일 헤더): 브라우저 확장이 연결돼 있지 않았다.
- GitHub Actions 실제 실행: 푸시하지 않았다.
- 실제 DB 백업, `hash_password` 대화형 실행, 작업 스케줄러 등록: 사용자 몫.
- 컨테이너에서의 의회·투자자 라우트, 뉴스 `warnings` 내용: 외부 호출을 아끼느라 부르지 않았거나 한 번만 불렀다.
- N-DEPLOY-10 수정 뒤의 재확인(`shift_clock2` +0/+20/+60/+400일, 이미지 재빌드 스모크): **대기**.

### 마지막 재확인 (14:19~, 코드 기준 최종 트리)

리드 알림: app-engineer가 N-DEPLOY-10의 1·2번을 고쳤고 이후 바뀌는 것은 문서뿐이다. 바뀐 파일 4개 — `backend/app/services/predictions.py`(13:54), `backend/tests/test_rules_api.py`(13:54), `backend/tests/test_ml.py`(14:03), `backend/tests/conftest.py`(14:20).

**N-DEPLOY-14 (정보 — 내 기록이 저장소의 가드 테스트를 깼다. 고쳤다.)**
- 현상: 2차 M절(14:1x에 추가)에 "개발자의 `.env`에 실매매 변수와 참 값을 등호로 이어 쓴 문자열"이 들어갔고, 저장소 파일을 훑어 실매매를 켜는 문자열을 찾는 `backend/tests/test_execution.py::test_no_file_turns_live_trading_on`이 `docs\dev\VERIFICATION.md:1726`에서 1건을 잡았다(리드가 단독 실행으로 확인, app-engineer의 +30·+400일 전체 실행도 이 1건만 실패).
- 원인: 내가 그 테스트의 존재를 알면서도(1차 H에서 그 값이 어디서도 켜지지 않음을 확인했다) 기록 문장에 리터럴을 그대로 적었다. 추가 직후에 돌린 내 누출 검사(`T_results.txt`의 "live trading switched on 1건")도 같은 줄을 잡았는데, 재확인보다 먼저 읽고 고치지 않았다.
- 수정(14:19, 리드 지시로 "추가만" 규칙의 예외): 그 문장만 "실매매 값을 켜 두었더라도(변수 이름에 참 값)"으로 바꿨다(`fix_record_line.py`, 내 절 앞부분의 바이트는 전후 동일함을 단언). 그 테스트의 `PATTERNS` 4개를 `VERIFICATION.md` 전체에 다시 돌려 **0건**.
- 검증: `py -3.11 -m uv run pytest tests/test_execution.py -o addopts="" -q` → **12 passed**. 아래 전체 실행에서도 통과.
- 교훈: 검증 기록을 추가한 뒤에는 `tests/test_execution.py`를 한 번 돌린다. 변수 이름과 참 값을 붙여 쓰지 않는다.

**N-DEPLOY-10 수정 확인**

코드 검토:
- `services/predictions.py`: `PredictionService.__init__`에 `today: Callable[[], date] = date.today`가 생기고 `_history_start(config, today)`가 그 값을 받는다. `_history_start`의 호출부는 `forecast()` 한 곳(110행), `PredictionService`를 만드는 곳은 `deps.py:94` 한 곳이고 인자를 주지 않으므로 **실서비스 동작은 그대로**(기본값이 실제 시계). 같은 파일 205행의 학습 창(`date.today() - 365 × years`)은 그대로 남아 있다.
- `tests/test_ml.py`: `get_prediction_service`를 `PredictionService(market, artifacts_dir, today=lambda: TODAY)`로 바꿔 끼우는 줄과 그 도우미만 추가. 단언 8개는 그대로(`git diff`에서 지워진 줄은 import 한 줄).
- `tests/test_rules_api.py`: autouse fixture에서 `get_rule_service`를 `RuleService(…, today=lambda: TODAY)`로 고정. `RuleService`에는 원래 `today` 인자가 있어 프로덕션 변경 없음. 단언 변화 없음. 인자 구성은 `deps.get_rule_service`와 같다.
- `tests/conftest.py`: 환경 고정 목록에 실매매 변수를 꺼짐으로 넣는 한 줄(N-DEPLOY-11 제안 채택).
- 약해진 것은 없지만 두 테스트 모두 이제 `deps`의 기본 배선(인자 없는 생성)을 지나지 않는다. 기본 배선은 한 줄짜리라 위험은 작다.

`shift_clock2`(본문 시계까지 옮기는 내 플러그인)로 전체 pytest, 한 번에 하나씩(`N2_shift_a.log`·`N2_shift_b.log`·`N2_final.log`):

| 이동 | 수정 전 | 수정 후 |
| --- | --- | --- |
| +0일 | 1479 passed | **1479 passed** |
| +20일 (= 2026-12-01) | `test_ml` 1건 실패(단일 실행) | **1479 passed** |
| +60일 | (+45일에서 `test_ml` 1 failed) | **1479 passed** |
| +400일 | 2 failed(`test_ml`, `test_rules_api`) | **1479 passed** |
| 플러그인 없이, 지금 시계(최종 conftest) | — | **1479 passed (161초, 14:43 시작)** |

- 남은 것(고치지 않기로 한 것, 부분 실행으로 확인): `tests/test_forecasts_api.py` 10건은 +680일 통과·+800일 실패(수정 전에 좁힌 경계는 +680/+720 → **2028-09-21 ~ 2028-10-31 사이부터**), `tests/test_projection.py` 2건과 `tests/test_demo_mode.py` 2건은 +1500일 통과·+1900일 실패(**2030-12 ~ 2032-01 사이부터**). 같은 +800일 실행에서 `test_execution`·`test_ml`·`test_rules_api`는 통과(40 passed). 이 두 묶음은 리드·app-engineer가 고치지 않고 남은 위험으로 두기로 했다. ISSUE로 남겨 두지 않으면 그때 가서 원인을 다시 찾아야 한다.
- app-engineer가 보고한 수치와 대조: +0일 1479 일치. +30·+400일의 "1 failed"는 내 기록 문자열 때문이었고(N-DEPLOY-14) 고친 뒤 +400일은 위 표와 같다. +800일의 "11 failed"는 그 1건 + `test_forecasts_api.py` 10건이라는 설명과 위 부분 실행이 맞는다.

**M 재실행**(conftest에 한 줄이 늘어난 뒤, `M_results.txt`): 평범한 환경 **275 passed**, 적대적 환경 **275 passed**(각 66초). 한 줄 추가로 달라진 것 없음.

**이미지 재빌드**(14:21, `E2_build.log`): `docker build -t asset-manager-demo:verify .` exit 0, 이미지 `2133934c6050`(914MB). 12:38 이미지와 `/app` 파일 해시를 비교하면 **달라진 것은 `/app/app/services/predictions.py` 하나**다. 빌드 뒤 `backend/app`·`alembic`·`seed`·`scripts`·`pyproject.toml`·`uv.lock`·`frontend`·`Dockerfile`·`deploy`에서 바뀐 파일 없음(`find -newer`), 즉 이 이미지가 코드 기준 최종 트리의 이미지다.
- CI 스모크(P의 스크립트, 새 이미지): **10개 확인 실패 0** — 이미지 안 비밀·DB·모델 없음, 기동, 스모크 exit 0(`/api/predictions` 501 포함), 데모 잠금을 뺀 대조 실행은 exit 1.
- 로그인 인스턴스에서 `/api/predictions*` 5개(POST 포함) → 전부 501 `lstm_not_installed`(O의 스크립트, 10개 확인 실패 0).
- 실제 시세 seed와 컨테이너 전수(F·R)는 다시 하지 않았다. 바뀐 것이 torch가 없으면 501로 끝나는 LSTM 서비스의 시계 인자뿐이기 때문이다.

**누출 검사 재실행**(수정 47 + 신규 41, 88개 파일): 실매매를 켜는 줄 **0**, 해시 0, 불투명 긴 문자열 0, 추적·신규 파일 중 로컬 전용 0. 새로 걸린 것은 전부 이 기록이 T절에서 인용한 테스트용 가짜 값과 오류 문장이다(`VERIFICATION.md`의 `sk-ant-api03-FAKE-…` 인용 1건, 변수 이름이 든 오류 문장 4건).

**정리**: 내가 만든 컨테이너·볼륨·네트워크 없음(`docker ps -a`·`volume ls`·`network ls`를 시작 시점 목록과 비교), 검증용 이미지 태그는 내가 만든 세 개(`:verify`·`:verify-nocache`·내 compose가 만든 `:local`)를 전부 지웠다. 스크래치 서버 포트(8011~8018) 닫힘, 내 프로세스 없음. `deploy/.env` 없음, `%USERPROFILE%\asset-manager-backups` 생기지 않음. 8001 개발 서버는 처음부터 끝까지 건드리지 않았고 지금도 `/api/health` 200이다.
- 내 것이 아니어서 그대로 둔 것: 익명 볼륨 `2152ee7d…`(12:36:30 생성 — 그 시각에 나는 컨테이너를 띄우지 않았다. 가설: 다른 팀원의 스모크 컨테이너가 `-v` 없이 지워지며 남음), 이미지 `asset-manager-demo:probe`·`asset-manager-deps:probe`(리드), `backend/verify_empty.db-shm`·`-wal`(11-06의 이전 검증 세션이 남긴 무시 대상 파일 — N-DEPLOY-9와 같은 현상).
- **지금 떠 있는, 내 것이 아닌 컨테이너**: 14:40경부터 `asset-manager-demo-demo-1`(compose 기본 프로젝트 이름 `asset-manager-demo`, `127.0.0.1:8010`, healthy, 이미지 `asset-manager-demo:local` `976b356c…`, 볼륨 `asset-manager-demo_demo-data`, 네트워크 `asset-manager-demo_edge`)이 있다. 내가 띄운 것은 전부 `am-verify` 접두어였고 이것은 내가 만들지 않았다(리드나 사용자의 로컬 확인으로 보인다 — 가설). `docker ps -a`에 cloudflared 컨테이너는 없다. 건드리지 않았다.

### 최종 판정 (1·2차)

| 항목 | 판정 |
| --- | --- |
| A·J 재현 | 통과 — pytest 1479, ruff 2종, vitest 309, lint, build, gen:api 무변화 |
| B 로그인 전수 | 통과 |
| C 데모 전수 | 통과 |
| D 시작 거부 | 통과 |
| E·R 이미지 | 통과(재빌드 포함) |
| F 컨테이너 | 통과 |
| G 백업 | 통과 |
| H·T 누출 | 통과(N-DEPLOY-14는 내 기록의 문제였고 수정) |
| I·S 문서 | 통과 |
| K 정적 서빙 / L 로그인 + 정적 | 통과 |
| M conftest | 통과 |
| N 날짜 의존 | 1·2번 수정 확인, 3·4번은 남은 위험(2028·2030년대) |
| O torch 없는 경로 | 통과 |
| P CI | 통과(Actions 자체는 미실시) |
| Q 문구·규칙 | 통과(브라우저 미실시) |

- **커밋을 막는 것: 없음.** N-DEPLOY-10의 급한 부분(2026-12-01, 2027-11)은 고쳐졌다.
- **터널을 열기 전에 사용자가 끝내야 하는 것**: N-DEPLOY-6(8001에 로그인 켜기), 그리고 공개 직후 터널 경유 확인(방문자별 한도, https 쿠키, cloudflared 동작) — 내가 할 수 없었던 부분이다.
- **커밋 뒤로 미뤄도 되는 것**: N-DEPLOY-3·4·5·7·8·9·12·13(정보), N-DEPLOY-10의 남은 두 묶음(ISSUE로 남길 것), N-DEPLOY-1(보고의 수 정정).
- 브라우저로 본 것은 하나도 없다. 화면에 대한 판정은 전부 코드·번들·HTTP 응답에 근거한다.

## 기업 재무 지표 검증 (2026-11-12, verifier)

대상: D-036(종목별 기업 재무 지표)의 미커밋 작업 트리 — data-engineer(공급자 계약·yfinance 파서·Fake·서비스 캐시), app-engineer(모델·마이그레이션·스키마·라우터·화면), risk-engineer(데모 검토 목록). 코드·설정·다른 문서는 고치지 않았고 이 절만 추가했다.

전제와 방법:
- `backend/.env`, 실제 DB `backend/asset_manager.db`, 8001·5173 서버는 열지도 요청하지도 않았다. 스크래치 스크립트는 `Settings.model_config["env_file"] = None`으로 `.env`를 읽지 않게 하고 스크래치 DB만 썼다. 스크래치: `<스크래치>/verifier/fund/`.
- 실제 데이터 대조는 **AAPL, MSFT, KO, JPM, TSM, SPY, BTC-USD**만 썼다. Yahoo 조회는 종목당 1회(13:25, 20초 안에 전부)이고 AAPL만 D-1을 위해 13:33에 한 번 더 받았다. 그 뒤 분석은 전부 저장본(`real1/`, `real2/`)으로 했다. 사용자의 보유 종목은 모르는 채로 검증했고, 리드가 저장한 실제 응답 파일은 열지 않았다.
- 시각은 전부 2026-11-12 KST. app-engineer가 마지막 확인을 하던 중에 시작했다. 내가 본 변경: 13:12:46~47 `app/api/fundamentals.py`·`app/schemas/fundamentals.py`·`tests/test_fundamentals_api.py`, 13:14:08~55 프론트 `lib/fundamentals*`·컴포넌트 테스트 2개, 13:28:39~41 `openapi.json`·`schema.d.ts`(app-engineer의 `gen:api`). 그 뒤 코드 파일의 변경은 없다(`find -newermt`, 13:39와 끝에 다시 확인). 아래 수치는 따로 적지 않으면 **최종 트리**(13:39 이후 실행)의 것이다.

### A. 재현 — 통과

재현: `sh <스크래치>/verifier/fund/run_A_final.sh` → `A_final/summary.txt`(13:39:29~13:43:18). 1차 실행(13:13~13:31)의 로그는 같은 폴더의 `pytest_full.log`·`npm_test.log` 등.

| 무엇 | 결과 | 주장과 대조 |
| --- | --- | --- |
| `py -3.11 -m uv run pytest -o addopts="" -q -p no:cacheprovider`(전체) | **1755 passed**(177.9초; 1차 13:13 실행도 1755, 169.4초) | 브리핑의 1748은 13:12 변경 이전 수치다. app-engineer 최종 주장 1755와 일치 |
| 구성 | 직전 기준 1479 + `test_fundamentals.py` 229 + `test_fundamentals_api.py` 46 + `test_demo_mode.py` 신규 1 = 1755(`--collect-only` 파일별 수) | 일치 |
| `tests/test_fundamentals.py` / `test_fundamentals_api.py` / `test_demo_mode.py` / `test_execution.py` 따로 | 229 / 46 / 41 / 12 passed | data-engineer 229 일치, app-engineer 46 일치 |
| `ruff check . --no-cache` / `ruff format --check . --no-cache` | All checks passed / 196 files already formatted | 일치 |
| `npm test` | **49 files, 358 tests passed** | 브리핑의 350은 13:14 변경 이전. 최종 주장 358과 일치 |
| `npm run lint`(oxlint) / `npm run build` | exit 0(출력 없음) / exit 0 | 일치 |
| `npm run gen:api` 전후 sha256(13:33, 13:48 두 번) | `openapi.json` `52cda1f4…`, `schema.d.ts` `4f36291d…` — **전후 동일** | 일치. 실행 전에 사본을 뜨고 다르면 되돌리게 해 두었고 되돌릴 일은 없었다 |
| 마이그레이션(새 스크래치 DB, `mig_check.py`) | `heads` 1개 `5fa037bd0839`(down_revision `26d32d8e1b7a`) → `upgrade head` 뒤 `fundamentals` 테이블(symbol PK·fetched_at·attempted_at·payload JSON·error 300자, 전체 24개 테이블) → `alembic check` "No new upgrade operations detected" → `downgrade -1`로 테이블 삭제(23개) → `upgrade head` → `check` 통과 | 일치 |

- 13:16에 뜬 두 생성 파일의 해시와 13:31의 해시가 달랐다(app-engineer가 13:28에 note 코드가 늘어난 스키마로 다시 생성). 13:33 이후로는 바뀌지 않았다.

### B. 실제 데이터 단위·정의 독립 대조 — 통과 (발견 N-FUND-1·2)

재현: `python probe_real.py real1 AAPL MSFT KO JPM TSM SPY BTC-USD`(13:25:13~13:25:32, 종목당 1회) → `real1/<종목>.raw.json`(공급자가 실제로 받은 `info`·연간·분기 손익계산서, 같은 `Ticker` 객체)·`.result.json`(`get_fundamentals` 반환값). `python analyze_real.py real1 …` → `analysis_real1.txt`. 분석 스크립트는 앱 코드를 import하지 않고 원본 표에서 직접 다시 계산한다. yfinance 1.7.0.

| 확인 | AAPL | MSFT | KO | JPM | TSM |
| --- | --- | --- | --- | --- | --- |
| `per_trailing` vs 주가 ÷ `eps_trailing` | 38.8242 = 355.63 ÷ 9.16 | 27.1986 일치 | 28.7817 일치 | 14.3498 일치 | 25.6899 = 413.35 ÷ 원본 EPS 16.09(둘 다 달러, EPS 필드 자체는 None) |
| `pbr` vs 주가 ÷ `book_value_per_share` | 46.1079 일치 | 8.2260 일치 | 11.2317 일치 | 2.5956 일치 | None |
| `psr` vs `market_cap` ÷ Σ4분기 매출 | 10.7931 일치 | 11.1705 일치 | 8.2214 일치 | 4.7811 vs 4.5905(**+4.15%**, N-FUND-2) | None |
| `operating_margin_pct` vs `quarterly[0]` 영업이익 ÷ 매출 | 31.1250 일치 | 49.7567 일치 | 33.3707 일치 | None(두 표 모두 영업이익 행 없음) | 58.6582 일치 |
| `net_margin_pct` vs Σ4분기 순이익 ÷ Σ4분기 매출 | 27.6035 일치 | 41.1699 일치 | 28.6540 일치 | 33.2132 일치(Yahoo 값 34.59는 안 씀) | 51.1156 일치 |
| `revenue_growth_pct` vs `quarterly[0]` ÷ 1년 전 분기 − 1 | 11.7219 일치 | 18.8045 일치 | 7.4267 일치 | 8.0594 일치(Yahoo 값 10.2는 안 씀, 경고 로그 1건) | 50.9462 일치 |
| `dividend_yield_pct`(퍼센트 스케일) vs 배당 ÷ 주가 × 100 | 0.30 vs 0.304 | 0.74 vs 0.752 | **2.19** vs 2.173 | 1.93 vs 1.922 | 0.95 vs 0.912 |
| `debt_to_equity_pct` vs 총부채 ÷ (주당순자산 × 주식 수) × 100 | 84.286 vs 84.29 | 28.465 vs 28.47 | 107.449 vs 113.7 | None(Yahoo가 은행에는 값을 주지 않음) | 11.619(대조 불가: 통화 다름) |
| `roe_pct` vs 순이익 ÷ (주당순자산 × 주식 수) × 100(기말 자본 기준 근사) | 142.26 vs 117.9 | 34.22 vs 30.3 | 40.59 vs 39.1 | 18.01 vs 18.4 | 41.86(대조 불가) |

- "일치"는 소수 4자리까지 같다는 뜻이다. 영업이익률의 반올림은 소수 4자리다(브리핑의 "2자리"는 Fake 쪽이고 실제 파서는 `_PCT_DIGITS = 4`).
- 배당수익률은 Yahoo가 소수 2자리로 준 퍼센트를 그대로 쓴다(KO 2.19 — 0.0219도 219도 아니다). 부채비율·ROE도 퍼센트 스케일이 맞다(ROE의 차이는 평균 자본과 기말 자본의 차이, AAPL은 자사주 매입으로 자본이 작아 차이가 크다).
- **JPM(은행)**: `operating_margin_pct`·`debt_to_equity_pct`만 None이고 나머지 13개 수치와 손익계산서(영업이익 칸만 None)는 나온다.
- **TSM(ADR)**: `currency` = `TWD`, `market_cap`·`pbr`·`psr`·`eps_trailing`·`eps_forward`·`book_value_per_share` 6개가 None. 한 통화 안의 비율(이익률·성장률·ROE·부채비율)과 PER은 나온다.
- **SPY**: `Ticker`·`info` 두 번만 접근(`quoteType` = `ETF`)하고 손익계산서 요청 없이 None. 서비스가 이를 `supported=False`로 저장하는 것은 C에서 확인.
- **BTC-USD**: `yfinance` 모듈을 건드리면 실패하는 대역으로 바꿔 놓고 호출 → None, 접근 **0회**(`BTC-USD.result.json`의 `yf_calls: []`).
- `annual`·`quarterly`는 최신순이고 4개·5개 상한을 지킨다(원본은 5~7개 열). 반환된 행 45개 전부 원본 칸과 같은 값이다(`equals_raw=True`). 금액은 통화의 원 단위다: AAPL 2026 회계연도 매출 478,834,000,000(약 4,788억 달러), TSM 분기 매출 1,494,243,284,000(TWD).

**[N-FUND-2] (경미) 은행은 PSR의 매출과 손익계산서의 매출이 다르다** — JPM `psr` 4.7811은 `marketCap ÷ info.totalRevenue`(1,907억 달러)이고, 같은 응답의 분기 4개 `Total Revenue` 합은 1,987억 달러다(+4.15%). 순이익률은 손익계산서 합으로(33.21%), PSR은 Yahoo의 다른 매출 정의로 계산되어 한 카드 안에서 분모가 다르다. 파서의 PSR 대조 기준이 `info.totalRevenue`라 5% 허용 안에서 통과한다. 제안: PSR도 Σ4분기 매출이 있으면 그것과 대조하거나(어긋나면 None), ISSUE-058에 "은행은 매출 정의가 달라 PSR과 순이익률의 분모가 다르다"를 적는다. 커밋을 막지 않는다.

### D. 리드가 관찰한 이상 징후 2건

**D-1. `eps_trailing`이 조회 시점에 따라 2~12% 달랐다 — 파서가 아니라 Yahoo 값이 바뀐다(확인, N-FUND-1)**

재현: `diff_info.py`(AAPL 13:25 대 13:33), `peek_team_probe2.py`·`compare_days.py`(팀 스크래치의 11-11 17:59 원본 탐침 `probe_raw.json`을 허용 종목 AAPL·MSFT·TSM만 걸러 읽음, 다른 종목 키는 가림), `replay_team_raw.py`(같은 11-11 원본을 오늘 파서에 넣어 11-11 파서의 출력과 대조), `eps_vs_statement.py`.

1. **읽는 키**: `_first(info, "trailingEps", "epsTrailingTwelveMonths")`. 저장한 응답 8개(11-12의 5종목, 11-11의 3종목) 전부에서 두 키의 값이 같다. 키 선택은 원인이 아니다.
2. **몇 분 간격 재조회**: AAPL 13:25 대 13:33 — `info` 188개 키 중 달라진 것은 `fulldayChange`·`fulldayChangePercent` 둘뿐, EPS 관련 키와 파서 출력 전체가 동일. 요청마다 흔들리는 값이 아니다.
3. **파서 변경 전후**: 11-11 원본(AAPL·MSFT·TSM)을 오늘 파서에 넣으면 11-11 파서 출력과 다른 필드는 `operating_margin_pct`·`net_margin_pct`·`revenue_growth_pct` 셋뿐이고(반올림 수준, 예: AAPL 11.7 → 11.7219) `eps_*`·`per_*`는 같다. 손익계산서 우선으로 바꾼 것은 EPS를 건드리지 않았다.
4. **Yahoo 값 자체의 변화**(11-11 17:59 응답 → 11-12 13:25 응답, 같은 분기·같은 순이익·같은 주식 수):

| | 주가 | `trailingEps` | `trailingPE` | 손익계산서의 Diluted EPS |
| --- | --- | --- | --- | --- |
| AAPL | 348.51 → 355.63 (+2.04%) | **8.98 → 9.16 (+2.00%)** | 38.810 → 38.824 (+0.04%) | 회계연도(= 최근 12개월) 8.98 |
| TSM | 396.48 → 413.35 (+4.26%) | **15.43 → 16.09 (+4.28%)** | 25.695 → 25.690 (−0.02%) | Σ4분기 491.28 TWD(달러 환산은 환율이 필요) |
| MSFT | 533.16 → 521.125 (−2.26%) | 19.16 → 19.16 | 27.827 → 27.199 (−2.26%) | Σ4분기 19.16 |

- AAPL과 TSM은 이익이 그대로인데 Yahoo가 **PER을 거의 고정한 채 EPS를 주가 변동만큼 바꿔** 보냈다. AAPL의 손익계산서 EPS는 8.98이므로 11-12 응답의 9.16은 재무제표가 주는 값이 아니고, 그날 주가로 계산한 PER은 39.60인데 응답은 38.82다(−2.0%). MSFT·KO·JPM은 정상이다(`trailingEps`가 Σ4분기 Diluted EPS와 ±0.4% 안, PER이 주가를 따라 움직임).
- 그래서 같은 종목을 주가가 바뀐 뒤(또는 Yahoo가 값을 갱신한 뒤) 다시 받으면 EPS가 그날 주가 변동만큼 달라진다. 리드가 본 2~12%와 같은 종류의 현상이다. 다만 리드의 두 번(약 90분 간격, 주가 동일)을 그대로 재현하지는 못했다: 내 두 번(8분 간격)은 같았고, 리드의 저장본은 실제 보유 내역이라 열지 않았다. **가설**: Yahoo가 일부 종목의 `trailingEps`를 주가와 묶어 갱신하며 그 갱신이 리드의 두 조회 사이에 있었다. 원인(Yahoo 내부)은 확인할 수 없다.

**[N-FUND-1] (보통) `eps_trailing`·`per_trailing`은 손익계산서와 대조되지 않고, Yahoo가 준 값이 재무제표와 어긋나도 그대로 나간다**
- 현상: 위 표. AAPL 11-12 응답의 `eps_trailing` 9.16은 같은 응답의 연간 손익계산서 Diluted EPS 8.98보다 2.0% 크고 `per_trailing` 38.82는 주가 ÷ 8.98 = 39.60보다 2.0% 작다. TSM은 4.3%.
- 원인: 파서의 대조 `trailingPE ≈ price ÷ trailingEps`는 Yahoo 값끼리의 대조라 둘이 함께 어긋나면 통과한다(`_multiple`). "손익계산서 우선"은 이익률·성장률 세 개에만 적용됐다.
- 영향: 화면이 "EPS — 1주당 순이익 (최근 12개월)"과 "PER"을 기준일과 함께 사실로 보여 주는데, 주가가 크게 움직인 다음 날 받은 값은 그 변동 폭만큼 틀릴 수 있다. 24시간 캐시라 하루 동안 그대로다.
- 제안(data-engineer): 분기 4개의 `Diluted EPS`가 모두 있으면 그 합(회계연도 끝이 최신 분기면 연간 칸)과 `trailingEps`를 대조하고, 어긋나면 손익계산서 EPS를 쓰고 PER을 `주가 ÷ 그 EPS`로 다시 계산하거나 둘 다 None으로 둔다(다른 필드와 같은 규칙). 통화가 다른 ADR은 대조할 수 없으니 지금처럼 Yahoo의 PER만 남긴다. 최소한 ISSUE-058에 이 현상과 수치를 적는다.
- 커밋을 막는 결함은 아니다(값의 출처·기준일은 화면에 있고 오차는 하루 주가 변동 폭). 다만 D-036 2번("어긋나면 None")의 취지에 비추면 고치는 쪽이 맞다.

**D-2. 순이익률 50% 초과·매출 성장률 300% 초과 — 허용 종목 범위에서는 원본이 그런 값이다(부분 확인)**
- 내가 쓸 수 있는 종목 중 순이익률이 50%를 넘는 것은 TSM(51.1156%)이다. 손으로 확인: 분기 4개 순이익 763,064,422,000 + 706,561,938,000 + 572,479,752,000 + 485,465,363,000 = 2,527,571,475,000, 매출 1,494,243,284,000 + 1,270,380,250,000 + 1,134,103,440,000 + 1,046,090,449,000 = 4,944,817,423,000 → 51.1156%. Yahoo 자신의 `profitMargins`도 0.51116이고 일회성으로 튀는 분기는 없다(분기별 46~56%). **파서 오류가 아니다.**
- 매출 성장률 300% 초과는 허용 종목에 없어 재현하지 못했다(최대 TSM 50.9%). 코드로 보면 `revenue_growth_pct`는 `quarterly[0].revenue ÷ (350~380일 전 분기 매출) − 1`이고 분모가 0 이하이면 None이다. 1년 전 분기 매출이 작으면 산술적으로 300%를 넘으며 상한·안내는 없다. 리드의 해당 종목은 `analyze_real.py`와 같은 계산(반환된 `quarterly[0]`과 1년 전 행으로 손계산)으로 확인하면 된다 — 응답 안에 행이 같이 있으므로 화면의 표만으로도 대조된다.
- **안내 유무**: `notes` 7개 코드에 극단값·일회성 이익을 알리는 코드는 없다. 화면은 그 값을 그대로 보여 준다 → N-FUND-3.

**[N-FUND-3] (경미) 순이익률이 100%를 넘거나 영업이익보다 순이익이 훨씬 큰 경우의 안내가 없다** — 순이익률 줄의 뜻풀이는 "매출 100원 중 세금까지 내고 남긴 돈 (최근 12개월)"인데, 영업 외 이익(지분 평가이익 등)이 큰 회사는 값이 100%를 넘을 수 있어 문장과 숫자가 맞지 않게 된다. 제안(app-engineer, 미뤄도 됨): 판정이 아닌 사실 코드 하나 — 최근 12개월 순이익이 같은 기간 영업이익보다 클 때 "순이익이 영업이익보다 커요(영업 외 손익 포함)". 지금 있는 `operating_loss_net_profit`과 같은 성격이다.

### C. 서비스·캐시 — 통과

14:02에 리드가 알렸다: N-FUND-1·2·3을 고치는 중이라 `app/data/yfinance_provider.py`·`provider.py`·`tests/test_fundamentals.py`(data-engineer, 13:59~)와 `app/api/fundamentals.py`·`app/schemas/fundamentals.py`·`tests/test_fundamentals_api.py`·프론트 파일(app-engineer)이 바뀌는 중이다. C의 대상인 `app/services/fundamentals.py`는 그대로다(sha256 `ab9a91c8…`, 수정 시각 11-11 18:34).

재현: `python service_check.py`(14:05, 스크래치 파일 DB `service_dbs/`, 시계 주입, FakeProvider가 아닌 내 대역 공급자) → `service_check.log` **36개 확인, 실패 0**.

| 확인 | 결과 |
| --- | --- |
| TTL 24시간 | 첫 조회 1회 → 23:59:59에는 요청 없이 같은 뷰 → 정확히 24:00:00에 다시 조회. 새 세션·새 서비스 인스턴스도 같은 캐시를 읽는다(프로세스 메모리 캐시 없음) |
| error_ttl 1시간 | 첫 조회 실패: `data=None`·`fetched_at=None`·`stale=True`·`error`·`supported=True`. 59:59에는 재시도 없음, 정확히 1:00:00에 재시도. 행에는 `payload` SQL NULL, `attempted_at`만 |
| 실패 시 마지막 값 유지 | 성공(t0) → 24시간 뒤 실패: 수치와 `fetched_at`은 t0 그대로, `stale=True`·`error`. 저장된 payload가 비트 단위로 같다(만들어 낸 값 없음). 30분 뒤에는 요청 없음, 1시간 뒤 재시도 성공이면 새 수치·`error=None`·`stale=False` |
| ETF(공급자가 None) | `supported=False`·`stale=False`·`error=None`, payload SQL NULL + `fetched_at`으로 저장, 23시간 뒤 요청 없음, 24시간 뒤 다시 조회 |
| 코인·`KRW-*`·`KRW=X`·`^GSPC` | 공급자 호출 0, 행 0, `supported=False` |
| `get_many` | 순서 유지, 중복 제거, 재무제표 없는 자산은 조회 없이 끼워 넣음 |
| 옛 스키마 payload | 필드 누락·필드 추가·이름 바뀜·숫자 자리에 문자열/bool·행의 필드 누락·날짜 형식 오류·dict 아님·symbol null 9종 모두 `from_payload` → None. TTL 안이어도 캐시 미스로 다시 조회. 다시 조회가 실패하면 반쪽 수치 없이 `data=None`·`fetched_at=None`·`stale`·`error` |
| 동시성 | 스레드 10개(각자 세션, 파일 DB, 조회 0.15초)가 동시에 `get_many([AAA,BBB,CCC])` × 5회: **매번 종목당 1회**, 10개 결과 동일. 실패 종목도 묶음당 1회(1시간 안 두 번째 묶음은 0회, 1시간 뒤 묶음은 1회) |
| 쓰기 순서 | 조회 4건이 도는 동안 행 수 0, 끝난 뒤 4(네트워크가 끝난 뒤 한 번에 기록) |
| 락 범위 | 락이 잡혀 있어도 캐시에 있는 종목은 바로 답한다 |

**변이 점검**(`make_mutants.py` → `run_mutants.sh`, 14:07, 원본 파일 불변 확인): 스크래치에 `backend/app`·`tests` 사본 3벌을 두고 `PYTHONPATH`로 사본을 물렸다(`which_app.py`로 사본이 import됨을 확인).

| 사본 | 팀 테스트 `-k "concurrent or lock"` | 내 `service_check.py` |
| --- | --- | --- |
| base(그대로) | 4 passed | 36개 통과 |
| m1: 락은 두되 "무엇을 받을지"를 락 **밖에서** 정함(재판정 제거) | **2 failed**(`…ask_the_provider_once_per_symbol`, `…try_a_failing_symbol_once_per_error_ttl`), 2 passed | C7 2개 실패 — 종목당 **10회** |
| m2: 락 제거 | **2 failed**(같은 두 개), 2 passed | C7 2개 실패 — 종목당 10회 |

- 동시성 테스트는 재판정이 빠지면 실제로 실패한다. 테스트가 장식이 아니다.
- 정보(결함 아님): 락을 네트워크 구간 내내 잡는다(의도, 모듈 주석). 공급자 호출이 멈추면 그 프로세스의 다른 갱신도 그동안 기다린다. yfinance 요청의 타임아웃에 기대는 구조이고 캐시에 있는 종목의 응답은 막히지 않는다.

### E. API — 통과 (최종 트리, 81개 확인 실패 0; 발견 N-FUND-5·6·9·11)

14:15에 리드가 알렸다: N-FUND-1·2·3 수정이 모두 들어와 코드 기준 최종 트리다(마지막 코드 변경 14:05:31 `tests/test_fundamentals.py`, 14:07 `openapi.json`·`schema.d.ts`). E·F·G와 "수정 후 재확인"은 이 트리에서 했다. `notes[]` 코드는 9개가 됐다.

재현: `python run_E.py`(14:28~14:29) → `E_results.txt`. 진짜 uvicorn + 진짜 `app.main.app`, 스크래치 DB, `AM_MARKET_PROVIDER=fake`. 공급자는 FakeProvider를 감싼 대역이다: 모든 호출을 기록하고, 지정한 종목의 `get_fundamentals`·`get_quote`를 실패시키고, note 조건마다 손으로 만든 `Fundamentals` 27개를 돌려준다(`scratch_server.py`). 인스턴스 3개(8041 빈 DB, 8042 합성 장부, 8043 데모)는 각 묶음이 끝날 때 내렸고 끝난 뒤 세 포트 모두 닫혀 있다. 외부 서비스 호출 0.

| 확인 | 결과 |
| --- | --- |
| `/held`, 보유 없음 | 200, `items: []`, `as_of: null`, 출처·고지 포함, 공급자 호출 0 |
| `/held`, 합성 장부(AAA·CCC 주식, ETFX = 재무제표 없음, SOLD = 전량 매도, ETH-USD) | 200, `[AAA, CCC, ETFX]` — `/api/portfolio/holdings`의 주식 순서 그대로, 코인·수량 0 종목 없음, ETFX는 `supported=false`에 수치 전부 null, `as_of`는 수치 있는 항목 중 가장 오래된 날짜. 조회는 종목당 1회, 다시 불러도 추가 조회 0 |
| `/held`, 한 종목 갱신 실패 | 200 그대로, 그 항목만 `stale=true` + `error` + 마지막 수치, 목록 `as_of`는 그 오래된 날짜 |
| `/{symbol}` 주식(`aaa` → `AAA`) | 200, 필드 전부, 4번 요청에 조회 1회. Fake 수치가 서로 맞는다(PER × EPS = PBR × 주당순자산, PSR, 이익률, 성장률), 행은 최신순·상한 안 |
| `/{symbol}` 코인(`BTC-USD`·`btc`·`KRW-BTC`·`eth`) | 200 `supported=false`, 수치·날짜 없음, `stale=false`, 공급자 `get_fundamentals` 호출 0 |
| `/{symbol}` ETF(공급자가 None) | 200 `supported=false`, 수치 null, notes 없음, `stale=false`, `as_of` 있음 |
| 없는 종목(`NOPE`) | 404 × 3 |
| 형식 오류(`!!`·14자·`1ABC`·`DOGE-USD`·`A B`·`KRW=X`·`^GSPC`) | 전부 422, 공급자에 닿지 않음 |
| 첫 조회 실패 | **200** + `stale=true` + `error`("scratch outage for FAIL1") + `supported=true` + 수치·날짜 없음. 4번 요청에 조회 1회(1시간 보류) |
| 성공 뒤 갱신 실패(스크래치 DB의 행을 25시간 전으로 돌림) | 200 + `stale=true` + `error` + **수치·행·notes가 이전 응답과 동일**, `as_of`는 예전 날짜. 보류가 지나면(시도 시각을 2시간 전으로) 다시 받아 `stale=false`·`error=null` |
| 출처 | Fake에서 `source_ko` = "합성 데이터(오프라인 데모용)", 응답 본문 어디에도 "Yahoo" 없음. 고지에 "투자 조언이 아닙니다" |
| 데모(`AM_ENV=production`·`AM_DEMO_MODE=true`) 장부 밖 종목 5개 | 전부 403 `demo_symbol_not_allowed`, 그 시점까지 **공급자 호출 0** |
| 데모 장부 종목·코인·`/held` | 200(코인은 `supported=false`), 공급자가 받은 `get_fundamentals`는 장부 주식 3개 각 1회뿐. POST·PUT·DELETE는 403 `demo_read_only` |

**note 코드 9개의 조건**(종목당 조건 하나, 기대 목록과 정확히 일치 27/27):

| 코드 | 붙는 경우(확인) | 안 붙는 경우(확인) |
| --- | --- | --- |
| `per_negative_earnings` | PER 없음 + EPS −1.2 / EPS 0 / (EPS가 빠진 ADR) 12개월 순이익률 < 0 | PER 없음 + EPS 양수(대조 탈락) |
| `per_forward_negative_earnings` | 예상 PER 없음 + 추정 EPS −0.5 | 추정 EPS 자체가 없음 |
| `operating_loss_net_profit` | PER 있음 + `quarterly[0]` 영업이익 < 0 | 분기는 흑자·연간만 적자 |
| `operating_loss_net_profit_annual` | PER 있음 + `quarterly[0]` 영업이익 없음 + `annual[0]` < 0 | 분기 값이 있으면 연간은 보지 않음 |
| `operating_income_not_reported` | 영업이익률 없음 + 모든 행에 영업이익 없음 | 영업이익률이 있으면 안 붙음 |
| `zero_revenue_quarter` | 영업이익률 없음 + 최신 분기 매출 0 | 영업이익률만 없고 행은 정상(이유 미상 → 코드 없음) |
| `net_income_above_operating_income` | 연속 4분기 Σ순이익 600 > Σ영업이익 400 > 0 | 순이익률 null / 순이익 = 영업이익 / Σ영업이익 0 이하 / 4분기는 정상인데 연간만 해당 |
| `net_income_above_operating_income_annual` | 분기 3개뿐이거나 분기 사이에 공백 + `annual[0]` 순이익 > 영업이익 > 0 | 4분기 합을 만들 수 있으면 연간은 보지 않음 |
| `currency_mismatch` | 통화 TWD + 6개 필드 전부 null | 6개 중 하나라도 있음 / 통화 USD / 통화 null |

- 함께 붙는 경우: 최신 분기만 영업적자(−5)이고 4분기 합은 흑자(595)이며 순이익 합(600)이 더 크면 `operating_loss_net_profit`(PER 줄)과 `net_income_above_operating_income`(순이익률 줄)이 같이 붙는다. 두 문장은 기간이 다르고("최근 분기" / "최근 12개월") 둘 다 사실이라 모순이 없다. 4분기 영업이익 합이 0 이하이면 뒤의 것은 붙지 않아 같은 말을 두 번 하지 않는다.
- 저장한 실제 응답 5개를 최종 파서 → 캐시 payload 왕복 → `_notes`에 넣으면(`notes_on_real.py`) AAPL·MSFT·KO는 `[]`, JPM은 `["operating_income_not_reported"]`, TSM은 `["currency_mismatch"]`이다. payload 왕복은 5개 모두 원본과 같다.

**[N-FUND-5] (경미) note 분류가 라우터에 있다** — `app/api/fundamentals.py`의 `_notes`·`_four_quarter_sums`는 손익계산서 행을 합산·비교하는 계산이다. "계산 로직은 서비스에만 둔다"는 규칙의 문구에 어긋난다(app-engineer가 스스로 꼽은 1번). 또 "연속 4분기"의 정의(80~100일)가 공급자(`_QUARTER_GAP`)와 라우터(`_QUARTER_GAP_DAYS`)에 따로 있어 한쪽만 바뀌면 순이익률의 기간과 note의 기간이 어긋난다. 동작은 맞다. 제안: 순수 함수로 서비스 계층에 옮기고 상수는 한 곳에서 가져온다. 커밋 뒤로 미뤄도 된다.

**[N-FUND-6] (경미) 조회가 실패했고 저장된 수치가 없는 종목은 요청마다 `get_quote`를 한 번씩 부른다** — `_one`이 404 여부를 가리려고 시세를 묻는다. 없는 종목 `NOPE`를 3번 요청하면 `get_fundamentals`는 1회(보류)지만 `get_quote`는 **3회**다(시세 캐시는 없는 종목을 기억하지 않는다). 서비스 주석의 "상장폐지 종목이 요청마다 공급자를 두드리지 않는다"가 이 경로에서는 성립하지 않는다. 화면은 `retry: false`·staleTime 1시간이고 데모는 장부 밖 종목을 앞에서 막으므로 영향은 작다. 제안: 실패 행의 `error` 문구나 별도 표시로 "없는 종목"을 기억해 보류 시간 동안은 시세를 다시 묻지 않는다.

**[N-FUND-9] (경미) `as_of`가 UTC 날짜다** — 한국 시각 00:00~08:59에 받은 값은 전날 날짜로 표시된다(app-engineer 3번). 값이 더 오래돼 보일 뿐 틀린 수치는 아니다. 제안: 시각을 UTC ISO로 내려 화면에서 현지 날짜로 바꾸거나 문구에 "UTC"를 적는다. 미뤄도 된다.

**[N-FUND-11] (정보) `/held`는 시세 조회가 실패하면 502다** — `portfolio.holdings()`를 쓰기 때문이다(app-engineer 4번). AAA의 시세를 실패시키면 `/api/portfolio/holdings` 502, `/api/fundamentals/held` 502(`scratch quote outage for AAA`), `/api/fundamentals/AAA`는 200이다. 그때는 홈의 보유 목록도 같은 이유로 실패하므로 요약만 따로 숨는 일은 없다. 수량만 필요하니 장부에서 직접 읽으면 시세 장애와 분리할 수 있다(선택).

### F. 화면 규칙 — 통과 (코드·번들·테스트 대조, 브라우저 미실시)

재현: `npx rolldown src/lib/fundamentals.ts --file <스크래치>/fundamentals.bundle.mjs`로 최종 `lib/fundamentals.ts`를 스크래치에 묶고 `node format_check.mjs`(14:30) → `format_check.txt` **47개 확인 실패 0**. 컴포넌트 두 개는 읽어서 대조했다(둘 다 11-11 18:15 이후 변경 없음).

- **금지어**: 모듈이 내보내는 문자열 63개(라벨·뜻풀이·note 문구·안내문)에 추천·사세요·파세요·오를·예상 수익·저평가·고평가·싸다·비싸다 없음. 세 파일에서 이 단어가 나오는 곳은 `lib/fundamentals.ts`의 머리 주석과 금지어 정규식 정의 두 군데뿐이다(Grep).
- **색·화살표**: `lib/fundamentals.ts`·`FundamentalsCard.tsx`·`FundamentalsSummary.tsx`에 `text-gain`·`text-loss`·▲·▼·`PnL` 없음. 값은 전부 `text-ink`이고 부호만 쓴다(`−3.4%`, `+6.1%`).
- **기준 기간**: 영업이익률 "(최근 분기)", 순이익률 "(최근 12개월)", 매출 성장률 "최근 분기 매출, 1년 전 같은 분기 대비", 이익 성장률 "최근 분기 이익, 1년 전 같은 분기 대비", PER "(최근 12개월 이익)", EPS "(최근 12개월)", PSR "최근 12개월 매출". 공급자의 정의와 맞다(B, 수정 후 재확인).
- **없는 값**: null·undefined·NaN → "–". 배당수익률이 정확히 0이면 "배당 없음".
- **적자 PER**: "적자라 PER을 계산할 수 없어요". **예상 PER**: 뜻풀이 "증권가 추정 이익 기준(추정)".
- **출처·기준일·stale**: `Yahoo Finance · 2026-11-12 기준`, 갱신 실패·기한 경과면 `· 마지막으로 받은 값`, 카드에는 "새 값을 받지 못해 마지막으로 받은 값을 보여 줘요." + 오류 문구. 한 번도 못 받았으면 "지금은 재무 숫자를 받지 못했어요." 한 줄.
- **고지**: 서버가 주는 `disclaimer_ko`("공개된 재무 숫자이며 투자 조언이 아닙니다. …")를 카드와 홈 요약 바닥에 출처와 함께 적는다. 카드 머리에 "회사가 공개한 재무 숫자예요. 예측이나 매매 신호가 아닙니다."
- **홈 요약 숨김**: `held.error || !held.data || items.length === 0`이면 `null`(오류·로딩·보유 주식 없음). 컴포넌트 테스트에 같은 세 경우가 있다.
- **무효화**: 장부를 바꾸는 mutation 6개(거래 생성·수정·삭제·전체 삭제·통화 변환·가져오기 확정)가 모두 `useLedgerMutation`을 거치고 그 안에서 `['fundamentals', 'held']`를 무효화한다.
- **큰 금액 표기**(손계산과 대조, 전부 일치):

| 입력 | 손계산 | 함수 |
| --- | --- | --- |
| 478,834,000,000 | 4,788.34억 → 100 이상이라 정수 | `4,788억`(달러면 `4,788억 달러`) |
| 999,960,000,000 | 9,999.6억 → 반올림하면 10,000억이라 조로 올림 | `1.00조` |
| 5,168,079,831,040 | 5.168조 | `5.17조` |
| 99,999,999 | 9,999.9999만 → 억으로 올림 | `1.00억` |
| 123,456,789 | 1.2346억 | `1.23억` |
| 12,345 / 9,999 / 9,999.6 | 1.2345만 / 그대로 / 10,000으로 반올림 | `1.23만` / `9,999` / `1.00만` |
| −4,512,000,000 | −45.12억 | `−45.1억` |
| −0.4 | 0(음의 0 없음) | `0` |

- 배수(`0.85배`·`7.42배`·`28.4배`·`1,234배`), 퍼센트(`18.2%`·`−3.4%`·`+6.1%`·0은 부호 없음·배당 2자리 `2.19%`), 주당 금액(`$8.98`·`−$1.23`·`39.20 TWD`), 기간(`2025.09`)도 같이 확인했다.
- 정보: 홈 행의 "(영업적자)" 표시는 분기 기준·연간 기준 두 코드에 같은 낱말을 쓴다. 바로 옆 칸의 영업이익률(최근 분기)이 음수로 보이므로 틀린 표시는 아니지만 한 분기만 적자인 회사에도 붙는다(app-engineer 2번). 종목 상세의 문장은 "최근 분기"를 명시한다.
- **미실시**: 브라우저 확인(390px·다크 테마·실제 Yahoo 데이터 화면). 도구가 없다. app-engineer도 영업적자·은행·ADR·stale·실패 화면은 컴포넌트 테스트로만 봤다고 했다(6번) → 리드가 실제 앱에서 한 번 눈으로 볼 것.

### G. 규칙 위반 탐색 — 통과 (확인 요청 N-FUND-7, 정보 N-FUND-10)

- **yfinance import**: `backend/app`·`tests`·`seed`·`scripts`·`alembic` 전체에서 `import yfinance`는 `app/data/yfinance_provider.py` 한 곳, `yf.Ticker`·`yf.download` 사용도 그 파일뿐.
- **Fake·합성 대체**: `backend/app`에서 `FakeProvider`를 만드는 곳은 `deps.get_provider`의 `market_provider == "fake"` 분기뿐. `services/fundamentals.py`·`api/fundamentals.py`는 Fake를 import하지 않는다. 실패 경로는 C·E에서 `stale`·`error`와 마지막 값(없으면 null)만 나옴을 확인했다. Fake 실행의 응답은 출처를 "합성 데이터"라고 적는다.
- **비밀값**: 바뀐 19개(이 기록 제외) + 새 14개 파일에서 키·토큰·해시·긴 불투명 문자열 없음. 걸린 것은 기존 테스트의 시험용 문자열(`tests/test_demo_mode.py`의 `test-only …`)과 "risk-engineer" 같은 낱말뿐.
- **추적되면 안 되는 파일**: 새 파일 14개는 전부 소스·테스트·마이그레이션이다. DB·로그·`.env`·pickle 없음(`git status --short --untracked-files=all`). 내 스크래치는 저장소 밖이다.
- **쓰기 라우트**: 새 라우트는 GET 둘뿐이라 데모 쓰기 허용 목록은 그대로이고, `tests/test_demo_mode.py`의 검토 목록에 `/api/fundamentals/{symbol}`이 올라 있다(41 passed).

**[N-FUND-7] (보통, 리드 확인 요청) 파서 주석에 저장소에 처음 나오는 종목 이름이 있다** — `backend/app/data/yfinance_provider.py` 38행과 48~49행의 주석이 단위 확인에 쓴 종목을 이름으로 적는다. 그중 세 개(38행의 둘, 49행의 하나)는 HEAD의 어떤 파일에도 없던 이름이고, 48~49행의 두 종목은 리드가 실제 화면에서 어긋남을 본 뒤 추가로 탐침한 것이다. 나는 보유 목록을 모르므로 판정할 수 없다. **실제 보유 종목이 섞여 있으면** 공개 저장소 규칙("기록에 실제 보유 종목을 쓰지 않는다") 위반이니 리드가 대조해, 해당하면 이름을 지우고 "다른 두 종목"처럼 바꾼다. 해당하지 않으면 닫는다. 이 기록에는 그 이름을 적지 않았다.

**[N-FUND-10] (정보) 캐시 payload에 파서 버전이 없다** — 필드 구성이 같으면 옛 파서가 만든 값도 24시간 동안 그대로 읽힌다. 이번처럼 계산 규칙만 바뀐 경우(EPS·PER·PSR) 실제 DB의 `fundamentals` 행을 지워야 새 규칙의 값이 보인다(리드가 이미 한 번 한 절차). 제안: payload에 규칙 버전 숫자를 넣어 다르면 캐시 미스로 취급한다(선택).

### H. 수정 후 재확인 (N-FUND-1·2·3, 최종 트리) — 해소 확인, 새 발견 N-FUND-4·8

대상: data-engineer의 `yfinance_provider.py`(`_eps_ttm`·`_line`·`_last_four`·`_warn_if_far`, EPS·PER·PSR 손익계산서 우선)·`provider.py` 주석·`tests/test_fundamentals.py`, app-engineer의 note 코드 2개(`net_income_above_operating_income`·`_annual`)와 화면 문구. 새 Yahoo 조회는 하지 않았다.

**H-1. 재현**(`sh run_A.sh final2`, 14:15:58~14:19:40 → `A_final2/summary.txt`; `gen:api`는 14:22)

| 무엇 | 결과 | 주장과 대조 |
| --- | --- | --- |
| 전체 pytest | **1816 passed**(171.8초) = 1479 + 271 + 65 + 1 | 일치 |
| `test_fundamentals.py` / `test_fundamentals_api.py` / `test_demo_mode.py` / `test_execution.py` | 271 / 65 / 41 / 12 passed | 271·65 일치 |
| `ruff check` / `ruff format --check` | All checks passed / 196 files already formatted | 일치 |
| `npm test` / lint / build | **49 files, 362 tests passed** / exit 0 / exit 0 | 일치 |
| `gen:api` 전후 sha256 | `openapi.json` `52e5347c…`, `schema.d.ts` `a92931dd…` — 전후 동일 | 일치 |

**H-2. 저장본을 최종 파서에**(`replay_final.py real1`, 13:25에 공급자가 받은 객체를 pickle로 그대로 넣음 → `replay_final.txt`)

| 종목 | `eps_trailing` | `per_trailing` | `psr` | 손계산 |
| --- | --- | --- | --- | --- |
| AAPL | 9.16 → **8.98** | 38.8242 → **39.6024** | 10.7931(같음) | 분기 표 최신 열의 EPS가 비어 있어 연간 열(2026-09-30, 분기 표 최신 열과 같은 기말)의 Diluted EPS 8.98. 355.63 ÷ 8.98 = 39.6024 |
| MSFT | 19.16(같음) | 27.1986(같음) | 11.1705(같음) | 4.92 + 4.81 + 4.27 + 5.16 = 19.16 |
| KO | 3.39 → 3.40 | 28.7817 → 28.6971 | 8.2214(같음) | 0.93 + 1.03 + 0.91 + 0.53 = 3.40. 97.57 ÷ 3.40 = 28.6971 |
| JPM | 23.93 → 23.84 | 14.3498 → 14.4039 | 4.7811 → **4.5905** | 5.57 + 7.70 + 5.94 + 4.63 = 23.84. 시가총액 911,909,847,040 ÷ Σ4분기 매출 198,653,000,000 = 4.5905 |
| TSM | None(그대로) | 25.6899(Yahoo 값 그대로) | None | 통화가 달라 대체 경로 |

- 다른 필드와 손익계산서 행 45개는 13:25 출력과 같다. 경고 로그는 AAPL `trailingEps=9.16 is not the 8.98 …` 1건(+ 기존 JPM `revenueGrowth` 1건).
- 팀의 11-11 원본(AAPL)을 같은 파서에 넣으면 EPS 8.98, PER 38.8096(주가 348.51)이다. 즉 이틀 사이 **EPS는 8.98로 고정되고 PER이 주가만큼(+2.04%) 움직인다.** → **N-FUND-1 해소**(재무제표 통화 = 거래 통화이고 EPS 행이 있는 종목).
- JPM의 PSR이 순이익률과 같은 분모(Σ4분기 매출)를 쓴다. → **N-FUND-2 해소.**
- `net_income_above_operating_income`·`_annual`의 조건·문구·함께 붙는 경우는 E의 표대로 확인했다. 순이익률 줄에 붙고 홈 행에는 표시하지 않는다(테스트 `leaves the home row unmarked …`). → **N-FUND-3 해소.**

**H-3. 연간 열 경로("연간 기말 = 분기 표 최신 기말")가 틀린 12개월을 집을 수 있는가**(`replay_final.py`의 합성 사례, 시장 데이터 아님)
- 정상(S4): 회계연도가 최신 분기에 끝나고 그 분기 EPS 칸이 비면 연간 값 = 같은 12개월. 맞다. 분기 사이에 공백이 있어도 연간 열은 그 12개월이라 맞다. 기말 날짜가 하루라도 다르면 이 경로를 타지 않고 Yahoo 쌍으로 간다(S6, 안전한 쪽).
- **틀리는 경우(S5)**: 결산월을 바꾼 회사의 "연간" 열이 12개월이 아닐 때(예: 직전 기말 2025-12-31 다음에 2026-09-30, 9개월). 파서는 그 9개월 EPS 2.90을 최근 12개월 EPS로 쓴다(Yahoo 4.00, 경고 로그만). 드문 경우다. 제안: 직전 연간 열이 350~380일 앞일 때만 이 경로를 쓴다(연간 열이 하나뿐이면 지금처럼).

**[N-FUND-4] (보통, 일부 가설) 손익계산서 EPS가 Yahoo 값과 아무리 달라도 경고만 남기고 손익계산서 값을 쓴다**
- 현상(합성 사례): 분기 EPS가 0.50·0.50·5.00·5.00이고 Yahoo `trailingEps`가 2.00이면 `eps_trailing` 11.0·`per_trailing` 9.09가 나간다(S1). 분기 EPS 합이 2.00이고 Yahoo가 12.00이면 2.0·50.0이 나간다(S3). 둘 다 로그 한 줄뿐이다.
- 원인: `_warn_if_far`는 기록만 하고 계산값을 쓴다(테스트 `…whatever_yahoo_says`가 이 동작을 고정). 수정 전에는 Yahoo의 쌍이 나갔다.
- 왜 문제인가(**가설**, 실제 종목으로는 확인하지 못함 — 허용 종목에 해당 사례가 없다): ① 액면분할 직후 Yahoo의 분기 표가 분할 전 분기의 EPS를 소급 조정하지 않은 상태, ② 달러로 공시하지만 ADR 1주가 보통주 여러 주인 종목에서 표의 EPS가 보통주 기준인 경우. 이때 주가와 기준이 다른 EPS로 PER을 만들면 배수 단위로 틀린다. 재무제표 통화 = 거래 통화 조건은 이 둘을 걸러 내지 못한다.
- 근거: `replay_final.txt` PART 2의 S1·S3·S5. 실제 데이터에서 관찰한 Yahoo와 손익계산서의 차이는 0.3~0.4%(KO·JPM)와 주가 연동분 2.0%(AAPL)·4.3%(TSM)였다.
- 제안(data-engineer): 두 값이 크게(예: 1.5배 밖) 어긋나면 어느 쪽도 믿지 않고 EPS·PER을 None으로 둔다 — D-036 2번의 "어긋나면 None"과 같은 규칙이고, 주가 연동분은 이 폭 안이라 지금 동작이 유지된다. H-3의 연간 열 조건도 같이. 최소한 ISSUE-058에 한계로 적는다.
- 커밋을 막지는 않는다(실제 응답에서 본 결함이 아니다). 다만 보유 종목에 최근 분할 종목이나 ADR이 있으면 커밋 전에 넣는 편이 안전하다 — 그 판단은 보유 목록을 아는 리드 몫이다.

**[N-FUND-8] (정보, 한계) ADR의 PER은 Yahoo 값 그대로다** — TSM은 이틀 사이 주가가 +4.26% 움직였는데 응답의 PER은 25.695 → 25.690으로 그대로였다(EPS 15.43 → 16.09). 손익계산서의 Σ4분기 Diluted EPS는 491.28 TWD라 대조하려면 환율이 필요하다. 이번 범위 밖으로 두기로 했고(리드), 화면에는 통화 불일치 안내가 붙는다. ISSUE-058에 수치와 함께 적어 둘 것.

### app-engineer가 꼽은 확인점에 대한 의견

1. note 분류가 라우터에 있음 → 규칙 문구에는 어긋난다. N-FUND-5(경미, 미뤄도 됨).
2. `operating_loss_net_profit`이 한 분기 적자에도 붙음 → 문장이 "최근 분기"를 명시하고 조건도 그 문장 그대로라 사실 서술이다. 문제 아님. 홈의 짧은 표시만 기간이 없다(F의 정보).
3. `as_of`가 UTC 날짜 → N-FUND-9(경미).
4. `/held`가 시세 실패 시 502 → 재현했다. 그때는 보유 목록도 같이 실패하므로 받아들일 만하다. N-FUND-11(정보).
5. 홈을 열면 접혀 있어도 조회가 나감 → 맞다(훅이 컴포넌트 최상단). 종목당 24시간에 1회이고 동시 요청은 락으로 한 번만 나가며(C) 데모는 장부 종목만 조회한다(E). 받아들일 만하다.
6. 390px·다크·실제 데이터 화면을 눈으로 보지 못함 → 나도 보지 못했다(도구 없음). 리드가 실제 앱에서 확인할 것.

### 정리

- 스크래치 인스턴스(8041·8042·8043)는 전부 내렸고 포트가 닫혀 있다. 8001·5173은 건드리지 않았고 요청도 보내지 않았다(8001 프로세스의 시작 시각은 14:15:39로, 수정이 들어온 뒤 리드가 다시 띄운 것이다. 그 무렵 실제 DB의 `-wal`·`-shm`과 서버 로그의 수정 시각이 바뀐 것도 그 때문이고 내 실행과는 무관하다). `backend/.env`·실제 DB는 열지 않았다.
- 저장소에서 내가 바꾼 것은 이 절뿐이다. `gen:api`는 세 번 돌렸고 매번 결과가 같아 두 생성 파일의 내용은 그대로다(수정 시각만 바뀜). `npm run build`가 `frontend/dist`(무시 대상)를 다시 만들었다.
- Yahoo 조회: 13:25에 6종목 각 1회(BTC-USD는 요청 없음), 13:33에 AAPL 1회. 그 밖에는 없다.

### 최종 판정

| 항목 | 판정 |
| --- | --- |
| A 재현 | 통과 — pytest 1816, ruff 2종, vitest 362(49 files), lint, build, `gen:api` 무변화, 마이그레이션 왕복 |
| B 실제 데이터 단위·정의 | 통과 — 5종목 × 9개 대조, ETF·코인 경로. N-FUND-1·2는 수정 후 해소 |
| C 서비스·캐시 | 통과 — 36개 확인, 변이 2종 모두 테스트가 잡음 |
| D-1 EPS가 시점마다 다름 | 원인 확인(Yahoo 값이 주가를 따라 바뀜) → 수정 후 해소. ADR은 한계로 남음(N-FUND-8) |
| D-2 극단값 | 허용 종목 범위에서는 원본 값(파서 오류 아님). 매출 성장률 300% 초과 사례는 미재현. 안내는 N-FUND-3으로 추가됨 |
| E API | 통과 — 81개 확인, note 9개 조건 27/27, 데모 가드 |
| F 화면 규칙 | 통과(코드·번들·테스트). 브라우저 미실시 |
| G 규칙 위반 탐색 | 통과. N-FUND-7은 리드 확인 필요 |
| H 수정 후 재확인 | N-FUND-1·2·3 해소. 새 발견 N-FUND-4 |

| 번호 | 심각도 | 상태 |
| --- | --- | --- |
| N-FUND-1 EPS·PER이 재무제표와 대조되지 않음 | 보통 | **해소**(H-2) |
| N-FUND-2 은행 PSR의 분모 | 경미 | **해소**(H-2) |
| N-FUND-3 순이익 > 영업이익 안내 없음 | 경미 | **해소**(E·H-2) |
| N-FUND-4 손익계산서 EPS를 무조건 채택(큰 어긋남·12개월 아닌 연간 열) | 보통(일부 가설) | 열림 |
| N-FUND-5 note 분류가 라우터에, 분기 간격 상수 중복 | 경미 | 열림 |
| N-FUND-6 실패 종목마다 요청당 `get_quote` 1회 | 경미 | 열림 |
| N-FUND-7 파서 주석의 종목 이름(보유 종목 여부 대조) | 보통(확인 요청) | 열림 |
| N-FUND-8 ADR의 PER은 Yahoo 값 그대로 | 정보(한계) | 기록만 |
| N-FUND-9 `as_of`가 UTC 날짜 | 경미 | 열림 |
| N-FUND-10 캐시에 파서 버전 없음(규칙을 바꾸면 행을 지워야 함) | 정보 | 기록만 |
| N-FUND-11 `/held`는 시세 실패 시 502 | 정보 | 기록만 |

- **커밋 전에 할 것**: N-FUND-7(리드가 주석의 종목 이름을 보유 목록과 대조, 해당하면 삭제). N-FUND-4는 보유 종목에 최근 분할 종목·ADR이 있으면 커밋 전에, 없으면 ISSUE-058에 한계로 적고 뒤로.
- **커밋 뒤 실제 앱에서 할 것**: 실제 DB의 `fundamentals` 행을 지워 새 규칙의 값이 보이게 한다(N-FUND-10). 브라우저로 종목 상세·홈 요약을 한 번 본다(390px·다크 포함).
- **뒤로 미뤄도 되는 것**: N-FUND-5·6·9·11, N-FUND-8(환율이 필요한 범위 밖 작업).
- 화면을 눈으로 본 것은 없다. 화면에 대한 판정은 전부 코드·번들·컴포넌트 테스트·HTTP 응답에 근거한다.

### 추가 (14:46 이후) — N-FUND-7 닫음, 주석 수정 뒤 재확인

리드가 14:46~14:47에 두 가지를 바꿨다고 알렸고 디스크에서 확인했다. 위의 "최종 판정" 표는 그 전(14:45) 상태이고 이 절이 마지막 상태다.

- **N-FUND-7 닫음**: 리드가 보유 목록과 대조했다 — 새 코드의 종목 이름은 해당 없음. 그래도 `backend/app/data/yfinance_provider.py` 머리 주석의 두 줄을 종목 이름 없이("a seventh name …", "an eighth …") 바꿨다(14:46:48). 대조 중에 이 파일의 **예전 절**(포트폴리오 코치 검증, 2026-10-27)의 두 줄에서 공개 규칙에 걸리는 티커 목록을 찾아 "티커 가림"으로 바꿨다(14:46:39, ISSUE-059). 그 두 줄과 파일 전체의 줄바꿈(CRLF → LF)은 리드의 변경이고 내 절의 내용은 그대로다. 이 절에는 그 이름들을 적지 않았다.
- **주석 수정이 코드에 영향이 없는지**(`ast_compare.py`, 14:48): 14:07의 내 사본(sha256 `0af3ed2d…`, H에서 검증한 그 파일)과 현재 파일(`1d2d4daf…`)의 구문 트리가 **동일**하다(코드·docstring 불변). 달라진 줄은 5개(2줄 삭제, 3줄 추가)이고 전부 주석 줄이다. 저장본 재생(`replay_final.py real1`)의 출력도 14:17의 것과 바이트 단위로 같다 — AAPL EPS 8.98·PER 39.6024, JPM PSR 4.5905 그대로.
- **다시 돌린 재현**(`sh run_A.sh final3`, 14:48:30~14:52:13 → `A_final3/summary.txt`): 전체 pytest **1816 passed**(171.2초), `ruff check` All checks passed, `ruff format --check` 196 files already formatted, `test_fundamentals.py` 271 / `test_fundamentals_api.py` 65 / `test_demo_mode.py` 41 / `test_execution.py` 12 passed, `npm test` 49 files 362 passed, lint·build exit 0. 리드의 주장(271 + 12 = 283 passed, ruff 2종 통과)과 일치.
- 같은 트리에서 C와 E도 한 번 더 돌렸다(14:51~14:53): `service_check.py` 36개 통과, `run_E.py` 81개 통과, 스크래치 포트 닫힘.
- 14:08 이후 코드 파일의 변경은 이 주석 수정 하나뿐이다(`find -newermt`, 14:53에 다시 확인; `openapi.json`·`schema.d.ts`의 14:22는 내 `gen:api`가 같은 내용으로 다시 쓴 것).

**바뀐 판정**

| 번호 | 상태 |
| --- | --- |
| N-FUND-7 | **닫음** — 리드 대조 완료, 새 코드에는 해당 없음, 주석은 일반 표현으로 바꿈, 예전 기록의 두 줄은 가림(ISSUE-059) |
| N-FUND-5·6·9·10·11 | 리드 판단으로 커밋 뒤로 미룸. 14:53 현재 `TODO_FOR_ME.md`·`PROGRESS.md`에는 아직 이 번호들이 없다(리드가 적기로 함) |
| N-FUND-4 | 열림 — 커밋을 막지 않음. 가드를 넣을지, ISSUE-058에 한계로 적을지는 리드·data-engineer 결정 |
| N-FUND-8 | 한계로 기록(범위 밖) |

- **커밋을 막는 것: 없음.**
- 정보: 가려진 두 줄은 작업 트리에서만 바뀐 것이고 이미 올라간 커밋 이력에는 남아 있다. 이력을 정리할지는 사용자 결정이며 리드가 `TODO_FOR_ME.md`에 적어 두었다(ISSUE-059).
