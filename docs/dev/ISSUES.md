# ISSUES

팀이 찾은 문제를 모두 기록한다. 형식은 CLAUDE.md 「작업 기록」을 따른다.

범례
- 심각도
  - 치명: 지금 결과가 틀렸다. 다른 작업보다 먼저 고친다.
  - 높음: 전략 백테스트를 믿으려면 그 전에 반드시 고쳐야 한다.
  - 중간: 2단계 안에 고친다.
  - 낮음: 정확도나 편의에 관한 문제다.
- 원인에 "가설"이라고 적힌 것은 아직 확인하지 않았다는 뜻이다.
- 근거의 `file:line`은 커밋 c8216b6 기준이다.
- 1단계(진단, 2026-10-20)에서 등록한 항목은 verifier가 같은 날 검증했다. 판정은 조건부 통과이고 상세는 `VERIFICATION.md`에 있다. 각 항목의 '검증' 줄은 verifier가 갱신한다.
- 출처 표기: data=data-engineer, quant=quant-researcher, eval=evaluation-engineer, risk=risk-engineer. 원 보고서의 항목 번호를 함께 적는다.

## 상태 요약

| 번호 | 제목 | 심각도 | 담당 | 상태 |
|---|---|---|---|---|
| 001 | `final_only`가 봉을 언제 저장했는지 보지 않아 미완성 봉이 확정 봉으로 통과 | 치명 | data-engineer | 미해결 |
| 002 | 다시 받을 때 사라진 미완성 봉이 캐시에 남아 현재 모델 학습에 쓰임 | 높음 | data-engineer, quant-researcher | 미해결 |
| 003 | 서비스가 쓰는 run이 HEAD 코드보다 먼저 학습됨(학습·추론 피처 불일치) | 높음 | quant-researcher | 미해결 |
| 004 | OOS가 보유 종목만 저장되어 백테스트 대상이 실제 보유에 종속됨 | 높음 | quant-researcher | 미해결 |
| 005 | 홀드아웃 구간이 움직이고 열람 기록이 없으며 이미 두 번 열람됨 | 높음 | evaluation-engineer | 미해결 |
| 006 | OOS의 `fr`(종가→종가)을 손익에 쓰면 같은 봉 종가 체결이 됨 | 높음 | evaluation-engineer | 미해결 |
| 007 | `config_hash`가 하이퍼파라미터를 빼고 계산되고 `CONFIGS_TRIED`가 수동으로만 바뀜 | 높음 | quant-researcher, evaluation-engineer | 미해결 |
| 008 | edge가 전 자산 통합·전체 기간 기준이라 종목·시점 단위로 쓸 수 없음 | 높음 | evaluation-engineer | 미해결 |
| 009 | 전략 성과 검정이 없고 `report.compare`가 예측 열 이름에 묶여 있음 | 높음 | evaluation-engineer | 미해결 |
| 010 | Yahoo의 일시적 코인 봉 누락이 캐시 결측으로 남고, 패널은 봉 순번으로 shift함 | 높음 | data-engineer, quant-researcher | 미해결 |
| 011 | 실매매 플래그와 리스크 한도 설정이 없음 | 높음 | risk-engineer | 미해결 |
| 012 | 킬스위치·모의투자 기록·주문 관문이 없고 장부가 오염될 위험이 있음 | 높음 | risk-engineer | 미해결 |
| 013 | 불리언 파싱이 너무 관대해 실매매가 우발적으로 켜질 수 있음 | 중간 | risk-engineer | 미해결 |
| 014 | 테스트가 실제 `backend/.env` 값을 읽음 | 중간 | risk-engineer | 미해결 |
| 015 | `adj_close`가 배당을 세전으로 재투자해 원천징수 15%가 빠짐 | 중간 | data-engineer, evaluation-engineer | 미해결 |
| 016 | 코인을 USD 시세로 백테스트하면 업비트 KRW 손익과 달라짐 | 중간 | evaluation-engineer, data-engineer | 결정됨(D-014), 2단계 구현 |
| 017 | 기준선 ①(SPY·BTC 단순 보유) 자체가 MDD 20% 한도를 넘음 | 중간 | evaluation-engineer, risk-engineer | 미해결 |
| 018 | 보정하지 않은 p_up이 자산군마다 다른 방향으로 치우침 | 중간 | quant-researcher | 미해결 |
| 019 | 1d 신호는 비용과 회전율 때문에 불리함 | 중간 | quant-researcher | 미해결 |
| 020 | `LARGE_CAPS` 생존 편향 | 중간 | quant-researcher, evaluation-engineer | 미해결 |
| 021 | 공급자 경계에서 OHLC를 검증하지 않음 | 중간 | data-engineer | 미해결 |
| 022 | 실패나 결측을 조용히 다른 값으로 대체하는 경로 | 중간 | data-engineer, app-engineer | 미해결 |
| 023 | 환율 공백과 자산 간 달력 정렬 | 중간 | data-engineer | 미해결 |
| 024 | `^VIX`·`^VIX3M`·`^TNX` 종가가 장 마감 뒤 값일 수 있음(가설) | 중간 | data-engineer, quant-researcher | 미해결 |
| 025 | 실제 DB 시세 캐시가 사실상 비어 있음 | 중간 | data-engineer | 미해결 |
| 026 | `.gitignore`가 `.claude` 전체를 무시해 역할 정의가 커밋되지 않음 | 중간 | 사용자 | 보류 |
| 027 | `str(exc)`를 응답에 그대로 내보내는 패턴(향후 키 유출 경로, 가설) | 낮음 | risk-engineer, data-engineer | 미해결 |
| 028 | 홀드아웃 fold는 1년 내내 재학습하지 않음 | 낮음 | evaluation-engineer | 미해결 |
| 029 | 표본 기간 마지막 fold의 라벨이 홀드아웃 구간 가격을 사용 | 낮음 | evaluation-engineer | 미해결 |
| 030 | "backtest"라는 이름이 예측 OOS와 전략 백테스트에 겹침 | 낮음 | app-engineer | 보류 |
| 031 | 연도별 일관성이 부분 연도를 한 해로 셈 | 낮음 | evaluation-engineer | 미해결 |
| 032 | 셸에 `VIRTUAL_ENV`가 잡혀 있으면 `py -m uv`가 실패함 | 낮음 | 사용자 | 보류 |
| 033 | 문서·규칙 불일치(자리표시자, 추출기 기본값, 기록 폴더) | 낮음 | 리드, 사용자 | 미해결 |
| 034 | 백테스트 킬스위치 참고 집계가 연말 세금 납부를 일일 손실로 셈 | 낮음 | risk-engineer, evaluation-engineer | 해결됨 |
| 035 | 유명 투자자 데이터 출처의 품질 문제(ARK 펀드 갱신 중단, SEC User-Agent, 13F 중복 행) | 중간 | data-engineer, 사용자 | 부분 해결(SEC User-Agent는 사용자) |
| 036 | 스크린샷 가져오기가 수익률을 평균단가로 읽어도 미리보기가 `ok`로 통과시킴 | 높음 | data-engineer | 해결됨 |
| 037 | 범위 예측 `range_reason`이 검증 결과와 무관하게 `forward_test_pending`이라 화면이 "과거 검증 통과"로 과장 | 높음 | app-engineer(, evaluation-engineer) | 해결됨 |
| 038 | 홈 모델 상태 문장이 범위 기준선 우위를 "시장 평균보다 나았다"로 표현 | 중간 | app-engineer | 해결됨 |
| 039 | 1d 예측 `target_date`가 지난 날짜인데 "다음 거래일"로 표시 | 낮음 | app-engineer | 해결됨 |
| 040 | 추론 캐시 키가 세션 마감을 모르고 보유 주식의 마지막 봉 기준 예측이 하루 동안 만들어지지 않음 | 중간 | app-engineer | 해결됨(② 캐시 키) |
| 041 | Norges Bank 13F의 Q1·Q3 표가 기밀 처리로 비어 있어 최신 분기 스냅샷이 반년 동안 오류·stale | 중간 | data-engineer | 해결됨(직전 분기 fallback) |
| 042 | pypdf가 하원 PTR 양식의 small-caps 라벨 소문자를 NUL로 뽑아 행 구분이 깨짐 | 중간 | data-engineer | 해결됨(파서가 NUL 제거) |
| 043 | 백엔드가 `schema.d.ts`를 재생성한 뒤 하원 거래 테스트 픽스처가 `syncing`을 빠뜨려 `npm run build`(tsc)가 실패 | 중간 | app-engineer | 해결됨 |
| 044 | 하원 거래 카드의 "(하루 60건씩)" 문구가 백엔드 배치 동작·설정값과 다름 | 낮음 | app-engineer | 해결됨 |
| 045 | 하원 PTR 파서가 페이지 경계로 갈라진 금액 상한 행을 버리고, `D:` 둘째 줄을 가짜 unparsed로 세고, 점 표기 티커(`BRK.B`)를 정규화하지 않음 | 중간 | data-engineer | 해결됨 |
합계 45건: 치명 1, 높음 13, 중간 21, 낮음 10. 상태는 미해결 29, 해결·부분 해결 12, 보류 3, 결정됨 1(2026-10-23 갱신).

---

### [ISSUE-001] `final_only`가 봉을 언제 저장했는지 보지 않아 미완성 봉이 확정 봉으로 통과
- 현상: 코인 봉을 D일 마감 전에 캐시한 뒤 D+1 00:00 UTC가 지나서 다시 동기화하지 않고 읽으면, 그 미완성 봉이 확정 봉으로 반환된다. 합성 공급자로 재현했다(진짜 종가 2,146,985).
  - 10-19 23:55Z에 저장하고 10-20 00:05Z에 읽음(15분 TTL 안): 1,932,286(미완성) 반환
  - 10-19 06:00Z에 저장하고 10-20 00:40Z에 `max_age`=20h로 읽음: 1,932,286(미완성) 반환
  - 같은 조건에서 `max_age`=12h로 읽으면 다시 받아서 정상값이 나옴
- 원인: `get_history`는 `bar_is_final(symbol, date, now)`로 봉 날짜만 확인하고, 그 행을 봉 마감 후에 저장했는지는 보지 않는다. `price_bars`에는 저장 시각도 확정 여부 표시도 없다. `max_age` 경로와 15분 TTL 경로가 모두 동기화를 건너뛴다. `symbol_syncs.synced_at`은 현지(KST) naive 시각이다.
- 근거: `backend/app/services/market_data.py:100-106`(fresh 판정), `market_data.py:116-119`(final_only 판정). 재현 스크립트 `scratchpad\repro_partial.py`(data A1). 이 경로를 타는 호출처는 `backend/app/forecast/data.py:66`(참조 종목, `REFERENCE_MAX_AGE`=20h)과 `backend/app/services/forecasts.py:165`(track record, 12h).
- 해결: 2단계 wave A(data, 2026-10-21, D-016). 봉은 `bar_is_final(symbol, 날짜, synced_at)`일 때만 확정으로 돌려준다. `final_only` 읽기에서 지난 동기화 때 미완성이던 봉이 지금 마감됐으면 TTL·`max_age`와 무관하게 다시 받는다. `synced_at`은 naive UTC로 쓰고, 미래 시각이면 믿지 않는다. 스키마 변경 없음. `repro_partial.py` 5개 경우 모두 확정 종가 2,146,985.45 반환. 테스트 `test_market_data.py::test_bar_cached_in_progress_is_refetched_once_it_closes` 등 7개.
- 검증: verifier 확인(2026-10-20). `repro_partial.py`를 실행해 5개 경우 중 두 경우(15분 TTL 안, `max_age`=20h)에서 미완성 종가 1,932,286.90이 반환됐다(진짜 2,146,985.45). `market_data.py:99-106,116-119` 코드와 `synced_at`이 현지 naive 시각인 것도 확인했다.

### [ISSUE-002] 다시 받을 때 사라진 미완성 봉이 캐시에 남아 현재 모델 학습에 쓰임
- 현상: demo.db의 BTC/ETH/XRP/SOL 2026-10-19 봉이 다음 날 시가와 이어지지 않는다. 24시간 시장이라 D 종가와 D+1 시가는 거의 같아야 한다(정상 예: 10-18 종가 82,017.60, 10-19 시가 82,012.34).

  | 코인 | 10-19 종가(캐시) | 10-20 시가 |
  |---|---|---|
  | BTC | 82,800.32 | 81,844.43 (10-19 저가 81,942보다 낮음) |
  | ETH | 2,419.45 | 2,405.06 |
  | SOL | 105.20 | 104.93 |
  | XRP | 1.3078 | 1.3028 |

  Yahoo가 나중에 돌려준 BTC 10-19 확정 종가는 81,853.54다. 캐시 값 82,800.32보다 1.16% 낮고 10-20 시가와 이어진다. 따라서 캐시 봉은 미완성이었다.

  영향받은 것: 현재 모델 run `20261020T135115-4514d73e`(data_end 2026-10-19, 04:51 UTC 학습)에서 이 네 코인의 10-19 피처 행과, 기간별 타깃 한 행씩(1d는 10-18 행, 1w는 10-12 행, 1m은 09-19 행). 전체 패널 중 극히 일부다. 이 run으로 그 시점에 화면에 보여 준 예측도 영향을 받았다. `forecast_log`의 기준가(base_price)도 미완성 봉 값으로 저장됐지만, 채점은 캐시 adj_close를 다시 읽으므로 채점에는 영향이 없다. 실제 DB 캐시의 마지막 봉 하나도 그날 마감 전에 저장된 진행 중 봉이었다.
- 원인: Yahoo가 진단 시점(2026-10-20 07:00 UTC)에 10-19 코인 봉을 일시적으로 주지 않았다(07:36 UTC에 다시 받자 복구, ISSUE-010). 갱신은 upsert만 하고 응답에 없는 날짜를 지우지 않으므로, 그 사이 예전에 저장된 진행 중 봉이 남았다. 날짜가 지나자 ISSUE-001 때문에 "확정"으로 쓰였다. 미완성 봉이었다는 근거는 BTC 확정 종가 81,853.54와 캐시값 82,800.32의 차이(1.16%)다.

  이 상태는 영구적이지 않다. 다음 stale 동기화에서 마지막 봉 10일 전부터 다시 받아 upsert하므로 덮인다. 겹치는 구간에서 마지막 봉 하나만 다르면 `_rescaled`는 발동하지 않는다. 다만 그 사이에 학습이나 추론이 돌면 미완성 봉이 쓰인다. 현재 run `20261020T135115`는 이미 미완성 봉으로 학습됐다. 영구히 남는 영향은 이 run과 그 시점에 화면에 보여 준 예측이다.
- 근거: `backend/app/services/market_data.py:177-189`(stale 재동기화), `market_data.py:272`(`_upsert`), `backend/app/services/forecasts.py:154-180`(채점 경로), demo.db 조회(data A2, A9), verifier의 `gap.py` 재실행(07:36 UTC, VERIFICATION.md 반박·수정 1).
- 해결: 2단계 wave A(data, 2026-10-21, D-016). 다시 받은 결과에 없는 봉 중 저장 당시 미완성이던 것은 지운다(`_prune`). 저장 당시 확정이던 봉은 남긴다. 연속성 검사는 `app/data/quality.py`(코인 시가-전일 종가 0.5% 초과 `open_gaps`). 재학습은 quant 담당으로 남음.
- 검증: 부분 확인(2026-10-20). demo.db 수치는 그대로 확인했다. 07:36 UTC에 Yahoo가 10-19 봉을 다시 주며, BTC 확정 종가 81,853.54는 캐시 82,800.32와 +1.16% 다르다. 미완성 봉이었다는 근거가 된다. 다만 원인 중 'Yahoo가 10-19를 주지 않는다'는 일시적이었고, 다음 stale 동기화(OVERLAP 10일)의 upsert로 캐시는 스스로 고쳐진다. `forecast_log.base_price`는 track record 채점에 쓰이지 않는다(`forecasts.py:141` 저장, `:154-183` 채점은 캐시 adj_close를 다시 읽음). 심각도 재검토와 문서 수정 요청은 VERIFICATION.md 참고.

### [ISSUE-003] 서비스가 쓰는 run이 HEAD 코드보다 먼저 학습됨(학습·추론 피처 불일치)
- 현상: `current.json`은 13:51에 학습한 run `20261020T135115-4514d73e`를 가리킨다. 그 뒤 15:31 커밋 c8216b6에서 네 가지가 바뀌었다.
  - `FALLEN_COINS` 10종 추가
  - 주식 행의 `dxy` 지연을 0일에서 1일로 변경
  - `MIN_RANK_ASSETS` 추가
  - conformal을 보정 전(raw) 분위수 기준으로 수정

  두 run 모두 meta의 FALLEN_COINS가 0종이다. 그래서 추론 때 다음 두 가지가 학습 때와 다르다.
  - 서비스가 dxy를 1일 늦춰 만든 피처를, dxy를 당일로 학습한 모델에 넣고 있다.
  - 추론 때 `load_inputs`가 `reference_symbols()`로 FALLEN_COINS 10종까지 불러오므로, `latest_ranks`의 코인 순위 피처 비교군이 학습 때 15종에서 최대 25종으로 바뀐다(verifier V-1).

  저장된 conformal 오프셋, edge 판정, OOS도 HEAD 코드로 만든 것이 아니다. 디스크의 run OOS에는 HEAD 코드가 쓰는 `*_raw` 열이 없다. FALLEN_COINS 10종은 두 DB 어느 캐시에도 없다. Yahoo에서는 모두 받아진다(각 1,988~3,266봉, LUNC는 2022년 붕괴 포함). XMR(고점 대비 −16%)과 ZEC(−32%)는 지금 기준으로 "몰락한 코인"으로 보기 어렵다.
- 원인: 모델을 다시 학습하지 않은 채 패널과 유니버스 코드만 바뀌었다.
- 근거: `git show c8216b6 -- backend/app/forecast/{panel,universe,walkforward}.py`, `backend/artifacts/global/runs/*/meta.json`(quant A1), run의 `oos_{h}.csv.gz` 열 목록(`*_raw` 없음), `backend/app/forecast/data.py:85-99`, `backend/app/forecast/panel.py:233-259`(verifier V-1), `backend/app/forecast/universe.py:29-32,47`, `backend/app/forecast/panel.py:33`, 다운로드 확인 `scratchpad\fallen.py`(data A8).
- 해결: 2026-10-21 HEAD 코드로 재학습했다. run `20261021T163606-f5e2aae3`(설정 3, 해시 617b587dcee7, data_end 2026-10-20)이고 current.json이 이 run을 가리킨다(quant). XMR·ZEC는 FALLEN_COINS에서 뺐다(`universe.py`). `latest_ranks(..., peers=)`를 추가했고, meta["universe"]가 학습 때 순위 비교군을 기록한다. 남은 일은 두 가지다. ① 서비스(`services/forecasts.py:114`)가 `latest_ranks(panel, rows, peers=run.meta["universe"])`를 넘기는 것(app-engineer, D-011과 같은 시점) ② 데이터 수정이 끝난 뒤 리드 지시로 재학습(설정 3)하는 것.
- 검증: verifier 확인(2026-10-20). 두 run 모두 meta의 universe에 FALLEN_COINS가 0종이고 `config_hash`가 같다. 디스크 run의 oos에 HEAD가 쓰는 `*_q10_raw`/`*_q90_raw` 열이 없다. c8216b6 diff로 dxy 지연, MIN_RANK_ASSETS, raw conformal 변경을 확인했다. 추론 시 순위 피처 비교군에 FALLEN_COINS가 들어가는 불일치도 추가로 있다(VERIFICATION.md V-1).

### [ISSUE-004] OOS가 보유 종목만 저장되어 백테스트 대상이 실제 보유에 종속됨
- 현상: `oos_{h}.csv.gz`에는 사용자의 보유 종목만 들어 있다. report 점수는 유니버스 전체 표본 외 결과로 계산된다. SPY나 BTC-USD를 보유하지 않으면 기준선과 비교할 자료조차 없다.
- 원인: `train.py`가 화면 표시용으로 `backtests[h] = oos[oos["symbol"].isin(held)]`만 저장한다.
- 근거: `backend/app/forecast/train.py:99`, `backend/app/forecast/store.py:56-57`(quant A2, eval E-5).
- 해결: 완료(2026-10-21, quant). run `20261021T163606-f5e2aae3`(설정 3, 해시 617b587dcee7, data_end 2026-10-20)에 `oos_universe_{1d,1w,1m}`가 생겼다(68종, 보유 전용 종목 0). `train.py`가 `oos_universe_{h}.csv.gz`를 함께 저장한다. 내용은 참조 유니버스 전체이고 보유 전용 종목은 뺀다. 열은 oos_{h}와 같고 `universe_group`(strategy/large_cap/training_only)이 추가된다. 읽기는 `store.Run.universe_oos(h)`이다. `oos_{h}`는 그대로 둔다.
- 검증: verifier 확인(2026-10-20). `oos_1d/1w/1m` 세 파일의 종목 수가 meta의 held 수와 같고, report 점수는 유니버스 전체 OOS로 계산된다. `train.py:99`, `store.py:56-57`.

### [ISSUE-005] 홀드아웃 구간이 움직이고 열람 기록이 없으며 이미 두 번 열람됨
- 현상: 홀드아웃 시작일이 `dates.max() - 365일`이라 데이터가 늘 때마다 앞으로 밀린다. 그래서 새 홀드아웃의 대부분은 이미 본 구간이다. 학습할 때마다 홀드아웃을 채점하지만 몇 번 봤는지 기록하지 않는다. artifacts에 `data_end`=2026-10-19인 run이 두 개(11:25, 13:51) 있고 둘 다 report에 홀드아웃 점수가 있다. 그 사이 설정이 바뀌었다(ISSUE-007). quant의 순위 가설(H1)도 홀드아웃 IC를 본 뒤에 착안했다.
- 원인: 횟수 관리를 수동 상수 `CONFIGS_TRIED`(Bonferroni)에만 맡기고 있다.
- 근거: `backend/app/forecast/cv.py:35-36,49-52`, `backend/app/forecast/report.py:21-25`, `backend/app/forecast/train.py:78`, `backend/artifacts/global/runs/`의 run 두 개(eval E-1, quant A4).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). `cv.HOLDOUT_START = "2025-10-19"`로 고정하고 `PurgedWalkForward.fixed_holdout`의 기본값으로 썼다(D-019). 열람 기록은 `docs/dev/holdout_log.jsonl`(추가 전용)에 남긴다. `cv.open_holdout`은 같은 열람의 반복을 거부한다(전략은 설정 해시당 한 번, 예측은 (해시, data_end)당 한 번). 카운터를 올리지 않은 새 해시도 거부한다. 1단계의 두 열람은 소급 기록했다. 전략 홀드아웃은 `evaluation.open_strategy_holdout`이 돌려주는 `HoldoutAccess`가 있어야 날짜 범위(`holdout_window`)를 받을 수 있다. quant가 반영한 내용: `train(..., holdout_log=...)`가 walk_forward 전에 `open_holdout("forecast", ...)`를 부르고, 거부되면 학습 전에 멈춘다. `main()`은 `cv.HOLDOUT_LOG`를 넘기고 테스트는 None을 넘긴다. 남은 경로: `services/forecasts.py:426`의 앱 내 재학습은 holdout_log를 넘기지 않아 기록 없이 돈다(app-engineer 다음 투입 때 처리, D-011과 함께). wave B의 전략 홀드아웃은 `open_strategy_holdout`으로 한 번만 열고, 그 기록이 로그에 남아야 한다. 테스트는 `tests/test_forecast.py`의 `test_holdout_*`, `test_committed_holdout_log_*`.
- 검증: verifier 확인(2026-10-20). `cv.py:35-36`의 `dates.max() - 365일`을 확인했다. 두 run 모두 data_end 2026-10-19이고 report에 holdout 점수가 있다.

### [ISSUE-006] OOS의 `fr`(종가→종가)을 손익에 쓰면 같은 봉 종가 체결이 됨
- 현상: `fr_h = log p(t+h) − log p(t)`이고 p는 adj_close다. 이를 손익으로 쓰면 신호가 나온 봉 D의 종가에 체결한 것과 같아 CLAUDE.md 규칙 위반이다. 그런데 피처는 D 종가가 나와야 계산된다. OOS에는 시가(open)가 없다.
- 원인: 예측 라벨로 설계된 값이다(예측 용도로는 의도된 동작).
- 근거: `backend/app/forecast/panel.py:139-149`, `backend/app/forecast/walkforward.py:74-77`(eval E-6, quant A6).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). `app/strategy/backtest.py`의 `run_backtest`는 결정일 D의 다음 봉 시가에 체결한다(주식 다음 XNYS 세션, 코인 D+1 00:00 UTC). `fr`은 쓰지 않고, 분할 수정 open/close와 배당 이벤트를 쓴다(D-008, D-020). 테스트는 `tests/test_backtest.py`의 `test_fill_is_the_next_open_never_the_signal_bar`(체결일·체결가 확인)와 `test_position_on_bar_t_depends_only_on_signals_before_t`(cut 이후 결정을 바꿔도 cut일까지의 포지션·평가액이 같음)다.
- 검증: verifier 확인(2026-10-20). `panel.py:145`(`log_p.shift(-h) - log_p`)와 `walkforward.py:76`을 확인했고, oos 열에 open이 없다. 지금은 백테스트 코드가 없어 잠재 위험이다.

### [ISSUE-007] `config_hash`가 하이퍼파라미터를 빼고 계산되고 `CONFIGS_TRIED`가 수동으로만 바뀜
- 현상: 두 run의 `config_hash`가 `06aea83d5b7d`로 같다. 그런데 그 사이 하이퍼파라미터가 바뀌었다(조기 종료, `min_child_samples` 500, 학습률 0.02. models.joblib 5.97MB → 2.28MB). 첫 run의 report.json에는 `configs_tried` 키가 없다. 지금 값 `CONFIGS_TRIED`=2는 디스크의 run 두 개와 맞는다(`_prune`이 3개를 유지하므로 실행은 2번). 하지만 그 뒤 c8216b6에서 유니버스·피처·보정을 바꿨으므로 다음 학습은 세 번째 설정이다. 예전 LSTM(`app/ml`)을 같은 데이터에서 시도한 횟수에 넣을지도 정해지지 않았다.
- 원인: 해시가 피처 이름, 엔진, cv 설정만 포함한다. 하이퍼파라미터는 `models.py`에 하드코딩되어 있고, 유니버스와 CONTEXT 지연도 해시에 들어가지 않는다.
- 근거: `backend/app/forecast/train.py:46-48`, `backend/app/forecast/models.py:117,119`(LightGBM 학습률·min_child_samples), `models.py:92-93,151-162`(시간순 조기 종료), `backend/app/forecast/report.py:24-25`(eval E-2, quant A3).
- 해결: quant 부분 완료(2026-10-21). `train.run_config`가 해시 대상을 모은다. 대상은 panel 버전·상수, 피처, 모델 파라미터·분위수·조기 종료, 기준선 파라미터, cv, CONTEXT 종류·지연, 설계된 참조 유니버스다. 보유와 `CONFIGS_TRIED`는 해시에 넣지 않는다. meta에는 `config`, `config_hash`, `configs_tried`를 저장한다. 테스트는 `tests/test_panel.py`. 남은 담당: evaluation-engineer(`CONFIGS_TRIED`=3, 해시가 바뀌었는데 카운터가 그대로이면 막는 검사, 전략용 `STRATEGY_CONFIGS_TRIED` 신설, D-004). LSTM 포함 여부는 evaluation-engineer가 2단계에서 정해 DECISIONS.md에 기록한다. eval 부분(eval 2단계 wave A 구현(2026-10-21, verifier 검증 전)): `report.CONFIGS_TRIED`=3, LSTM은 세지 않음(D-018). 카운터 검사는 `cv.open_holdout`이 한다. 기록에 없는 새 해시인데 configs_tried가 기존 최댓값보다 크지 않으면 거부한다(D-019). train.py에서 호출하는 일은 quant에 요청했다. `STRATEGY_CONFIGS_TRIED`=2는 `app/strategy/evaluation.py`에 있다.
- 검증: verifier 확인(2026-10-20). `config_hash` 06aea83d5b7d가 같다. 첫 run report에 `configs_tried` 키가 없다. models.joblib 5,968,546 → 2,284,098 bytes. `_prune`은 현재 run 외 2개를 남긴다(`store.py:65-68`). 근거 줄 번호 수정 요청은 VERIFICATION.md 참고.

### [ISSUE-008] edge가 전 자산 통합·전체 기간 기준이라 종목·시점 단위로 쓸 수 없음
- 현상: edge는 기간(3) × 지표(2) 단위로 주식과 코인을 합쳐 판정한다. CLAUDE.md는 "edge가 없는 종목"이라고 하지만 종목별 edge는 없다. 판정에는 2016~2026 전체 표본 외 결과와 홀드아웃을 쓴다. 그래서 이 판정으로 2018년 신호를 켜고 끄면 미래 정보를 쓰는 셈이다. 현재 run은 6개 비교 모두 edge가 없다(PROGRESS.md 1단계 표). 이대로라면 모든 신호가 '우위 없음'이다.
- 원인: 설계상 단위가 풀링이고 판정이 한 번만 계산된다.
- 근거: `backend/app/forecast/report.py:90-121`, `backend/app/forecast/train.py:31-35`, `backend/app/services/forecasts.py:254`(eval E-3, quant A5).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). `report.compare_all`이 자산군 × 기간 × 지표(direction·range·rank) 18개를 한 Holm 묶음(m=18, 빠진 비교는 p=1로 채움)으로 판정한다. 시점 기준 edge는 `report.PointInTimeEdge.edge_at(as_of, asset_class, horizon)`이다. as_of까지 목표가 확정된 walk_forward 행만 쓰는 확장 창이다. 확정 여부는 실제 목표 종료 봉(`target_end_dates`)으로 판단한다(verifier B-1 수정, 휴장일 누수 제거). 이 창은 홀드아웃 행은 쓰지 않는다. 실서비스 순위 edge는 `FORWARD_CONFIRMED`가 비어 있어 항상 False(`forward_test_pending`)다(D-018). report 키가 `"{자산군}:{지표}"`로 바뀌어서 `services/forecasts.py`(app-engineer)가 읽는 `direction`/`range` 키는 다음 재학습 run부터 없다. 그래서 화면 edge는 app-engineer가 투입될 때까지 False다(안전한 쪽). 기준은 낮추지 않았다. 테스트는 `test_rank_comparison_*`, `test_point_in_time_edge_*`, `test_live_rank_edge_*`. 남은 일: quant(train.py에서 `compare_all` 사용, signals.py가 `report.EdgeStatus`를 import), app-engineer(화면에서 자산군별 키 읽기).
- 검증: verifier 확인(2026-10-20). `report.py:109-121`, `forecasts.py:254-255`. report.json의 6개 비교가 모두 edge False다.

### [ISSUE-009] 전략 성과 검정이 없고 `report.compare`가 예측 열 이름에 묶여 있음
- 현상: `compare`가 `{model}_q10`, `{model}_p_up` 같은 열을 직접 읽어서 수익률 시계열을 넣을 수 없다. 기준선 대비 초과수익 검정, Sharpe 차이 검정, Deflated Sharpe, 순위 정보(IC) 비교가 없다. Brier나 pinball 손실이 좋아진다고 비용 차감 후 수익이 나는 것은 아니다. 참고로 gbdt의 자산군 내 IC t는 walk_forward 구간에서 약 3이지만 edge 판정에는 들어가지 않는다.
- 원인: 예측 평가 전용으로 만들어졌다.
- 근거: `backend/app/forecast/report.py:78-106`, `backend/app/forecast/metrics.py:39-48,87-102`(eval E-4, quant B·C S1).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전).
  - `report.compare_losses(기준선 손실, 모델 손실, lags, 홀드아웃 쌍)`이 일반 함수다. 기존 `compare(oos, model, baseline, metric, lags)`는 그대로 쓸 수 있고, 기존 테스트 10개도 그대로 통과한다(합성 데이터 CV에 `fixed_holdout=None`만 추가).
  - `metrics`에 추가한 함수: `mean_test`(HAC t), `stationary_bootstrap_p`(Politis-Romano, 평균 블록 20일), `sharpe_difference`(Ledoit-Wolf 2008 HAC 델타 방법), `deflated_sharpe`(Bailey-López de Prado 2014), `wilson_lower`, `year_share`(부분 연도 제외).
  - 전략 검정과 D-015 ① 판정은 `app/strategy/evaluation.py`의 `excess_return_test`, `sharpe_test`, `adoption_gate`이고, `STRATEGY_CONFIGS_TRIED`=2다.
  - 순위 비교(자산군 내 IC 대 0, HAC t, Holm m=18, 연도 일관성, 홀드아웃)를 추가했다(D-018).
- 검증: verifier 확인(2026-10-20). `report.py:78-106`이 `{model}_p_up`/`{model}_q*` 열을 직접 읽는다. 전략 검정 함수는 없다.

### [ISSUE-010] Yahoo의 일시적 코인 봉 누락이 캐시 결측으로 남고, 패널은 봉 순번으로 shift함
- 현상: 2026-10-20 07:00 UTC 무렵 yfinance 1.7.0에 BTC/BNB/ADA를 10-16~10-20으로 요청하자 10-19 하루만 빠졌다. 그때 FALLEN_COINS 10종도 10-18까지만 왔다. 07:36 UTC에 verifier가 다시 요청했을 때는 BTC/BNB/ADA 모두 10-19를 반환했고, FALLEN_COINS도 10-19까지 왔다(봉 수 1,989~3,267). 그런데 그 사이에 동기화된 demo.db 캐시에는 10-20은 있고 10-19가 없는 코인이 AVAX를 포함해 11종 남아 있다(BNB, ADA, DOGE, TRX, LTC, LINK, AVAX, DOT, BCH, XLM, ETC). 과거 결측도 있다: AVAX-USD는 2020-07-15~09-21에 69일이 비어 있다(10-19를 합치면 70일). 패널의 타깃과 수익률은 날짜가 아니라 봉 순번으로 `shift`한다. 그래서 중간에 날짜가 빠지면 "1일" 수익률이 실제로는 2일 수익률이 된다.
- 원인: Yahoo 일시 누락이다(07:36 UTC 재요청 때 복구, 이유는 미확인). 일시적인 누락이라도 그 순간 받은 캐시에는 구멍이 남는다. 봉 순번 shift는 코드로 확인했다. 그래서 캐시의 결측이 패널에서는 기간이 어긋난 수익률이 된다. 따라서 달력 기준 결측 검사와 날짜 기준 shift는 여전히 필요하다.
- 근거: `scratchpad\gap.py`, `scratchpad\quality.py`(data A3), verifier의 `gap.py`·`fallen.py` 재실행(07:36 UTC, VERIFICATION.md 반박·수정 1, 3), `backend/app/forecast/panel.py:78-79,145`(`_log_ret`, `asset_targets`).
- 해결: data 쪽 2단계 wave A(2026-10-21). 달력 기준 결측 검사(`calendar.expected_dates`, `python -m app.data.quality`), 캐시 중간 결측 재요청(`MarketDataService.refill_gaps`), 엄격 로더는 결측이 있으면 예외. 추가 관찰: 10-21 01:46 UTC에도 Yahoo가 코인 23종 모두 10-20 봉만 빼고 10-21(진행 중) 봉을 줬다. 10-20 07:00 UTC의 10-19 누락과 같은 형태라 '자정 뒤 몇 시간 동안 전날 봉이 빠진다'는 가설로 본다(미확인). 다음 갱신의 겹침 구간에서 채워진다. AVAX 2020-07-15~09-21 69일은 재요청에도 Yahoo에 없다. 날짜 기준 shift는 quant 담당.
- 검증: 부분 확인(2026-10-20). 봉 순번 shift(`panel.py:78-79,145`)와 AVAX 2020년 공백(2020-07-15~09-21, 69일)을 확인했다. 07:36 UTC에 다시 요청하니 BTC/BNB/ADA와 FALLEN_COINS 10종 모두 10-19를 반환했다. Yahoo 누락은 일시적이었다. 10-19가 없는 코인은 10종이 아니라 AVAX를 포함한 11종이다.

### [ISSUE-011] 실매매 플래그와 리스크 한도 설정이 없음
- 현상: `Settings`에 `live_trading`, MDD 한도, 1회 주문 상한, 일일 손실 한도, 종목 비중 상한이 하나도 없다. `.env.example`에도 없다. `backend/app/strategy/` 디렉터리도 없다.
- 원인: 전략 단계를 아직 시작하지 않았다.
- 근거: `backend/app/config.py:11-41`, `backend/.env.example`(risk A1).
- 해결: 2단계 wave A 구현(risk-engineer, verifier 확인 전). `config.py`에 `live_trading`(기본 false), `risk_max_drawdown`(0.20, 0 < x ≤ 0.20), `risk_daily_loss_limit`(0.03), `risk_max_order_fraction`(0.05), `risk_max_order_krw`(선택, 빈 값은 미설정), `risk_max_position_weight`(0.20), `strategy_budget_stock`/`strategy_budget_crypto`(0.80/0.20, 합 ≤ 1), `paper_initial_capital_krw`(10,000,000)를 추가했다. `.env.example`에는 `AM_LIVE_TRADING=false`와 주석 처리한 기본값을 적었다. 레버리지·공매도 금지는 `risk.check_order`·`cap_weights`·`target_weights`의 고정 규칙이다. 테스트: `tests/test_risk.py`(기본값, 범위 밖 MDD 거부), `test_paper.py`(예산 합 > 1 거부), `test_execution.py::test_no_file_turns_live_trading_on`(저장소의 .py/.toml/.json/.md 등에서 실매매를 켜는 패턴 0건).
- 검증: verifier 확인(2026-10-20). `config.py:11-41`에 해당 필드가 없다. `.env.example`의 키는 2개뿐이다. `backend/app/strategy/`가 없다. 저장소 전체(.venv, node_modules 제외)에 `live_trading=true` 패턴은 0건이다.

### [ISSUE-012] 킬스위치·모의투자 기록·주문 관문이 없고 장부가 오염될 위험이 있음
- 현상: 주문 실행 코드, 킬스위치, 모의투자 테이블이 모두 없다. 지금 실제 주문이 나갈 경로는 없다. 보유 현황은 `transactions`에서 계산하므로 모의 체결을 `transactions`에 쓰면 실제 보유와 화면·예측·시뮬레이션이 모두 바뀐다. `app/db/models.py`와 마이그레이션은 어느 역할의 담당 파일 목록에도 없었다.
- 원인: 아직 구현하지 않았다. 역할을 정의할 때 DB 계층이 빠졌다.
- 근거: `backend/app/db/models.py`, `backend/alembic/env.py:7`, `backend/app/services/forecasts.py:44`(`held_symbols`가 `transactions`를 읽음), `.claude/agents/*.md`(risk A4, A5, A6).
- 해결: 2단계 wave A 구현(risk-engineer, verifier 확인 전).
  - `strategy/risk.py`: 백테스트와 공유하는 순수 함수(`cap_weights`, `target_weights`, `check_order`, `plan_rebalance`, `rebalance_orders`, `apply_decision`, `max_drawdown`, `adopt_strategy`, `kill_switch_triggers`, `portfolio_breach`). `backtest.py`가 그대로 import한다(D-003).
  - `strategy/execution.py`: 유일한 주문 관문 `execute`(킬스위치 → `check_order` → `live_trading is True`일 때만 `live_factory()`를 지연 호출, 지금은 NotImplementedError). `KillSwitch`는 `kill_switch_events`에 추가만 하고 최신 행이 상태다. 상태를 못 읽으면 발동으로 본다(fail-closed). 해제는 `actor="user"`만 가능하다.
  - `strategy/paper.py`: `python -m app.strategy.paper run|fill|score`. 추론(엄격 로더 `load_daily`만 사용, `services/forecasts.py` 경로 미사용) → `signals.decide`(S1-1w) → `risk.target_weights` → `execute`(paper) → `paper_signals` 기록. 매일 가상 계좌를 평가해 마지막 해제 이후 MDD·일일 손실 초과, 음수 현금·수량(leverage), 평가 불가(stale_data)면 킬스위치를 켜고, 켜진 동안의 신호는 `halted`로 기록하고 주문하지 않는다. 체결은 다음 봉 시가 ± 슬리피지와 전날 환율, 비용은 `backtest.CostModel`과 같다. 채점은 목표일 종가 총수익(배당 15% 원천징수)과 같은 기간 SPY/BTC. `transactions`에는 쓰지 않는다.
  - 테이블·마이그레이션: `models.py` 끝의 `KillSwitchEvent`, `PaperSignal`(유일 키 strategy_id·symbol·as_of), revision `e67d73f03bf8`. 실서비스 순위 edge는 D-006에 따라 꺼져 있어(`paper.no_live_edge`) 지금 기록은 모두 '우위 없음'이다.
  - 테스트: `tests/test_paper.py`(35건: 체결·장부·채점 순수 함수, FakeProvider로 run→fill→score 전 과정, 킬스위치 MDD·일일 손실·해제 후 재감시·stale_data·leverage·상태 읽기 실패, 승인 뒤 체결 전 발동이면 대기 주문 취소(해제해도 되살리지 않음), transactions 0행, 실매매 팩토리 호출 0회), `test_execution.py`(12건), `test_risk.py`(52건).
- 검증: verifier 확인(2026-10-20). `.claude/agents/*.md`의 담당 파일에 `app/db/`가 없다. `forecasts.py:44-49` `held_symbols`가 transactions를 읽는다. `alembic/env.py:7`.

### [ISSUE-013] 불리언 파싱이 너무 관대해 실매매가 우발적으로 켜질 수 있음
- 현상: `live_trading: bool`로 선언하면 pydantic이 `"1"`, `"yes"`, `"on"`, `"y"`, `"t"`를 모두 True로 받아들인다.
- 원인: pydantic의 기본 bool 변환 규칙이다.
- 근거: `TypeAdapter(bool).validate_python(s)` for `['yes','on','1','y','t']` → 모두 True(risk A2).
- 해결: 2단계 wave A 구현(risk-engineer, verifier 확인 전). `config.py`의 `_strict_bool`(`mode="before"`)이 bool 값과 `"true"`/`"false"`(대소문자 무시, 공백 제거)만 받고, `"1"`, `"yes"`, `"on"`, `"y"`, `"t"`, `"tru"`, 빈 문자열 등은 ValidationError로 시작을 실패시킨다. `execute`는 `settings.live_trading is True`(동일성 비교)일 때만 실매매 경로를 연다. 테스트: `test_risk.py::test_live_trading_rejects_anything_but_the_exact_words`.
- 검증: verifier 확인(2026-10-20). `TypeAdapter(bool)`이 'yes','on','1','y','t','TRUE'를 모두 True로 받는다.

### [ISSUE-014] 테스트가 실제 `backend/.env` 값을 읽음
- 현상: `get_settings()`는 `lru_cache`에 `env_file=backend/.env` 설정이고, conftest에 설정을 격리하는 장치가 없다. 사용자가 `.env`에서 실매매를 켜면 테스트도 그 값을 본다.
- 원인: 지금까지는 테스트가 설정값에 크게 의존하지 않았다.
- 근거: `backend/app/config.py:14-16,44-46`, `backend/tests/conftest.py`(risk A3).
- 해결: 2단계 wave A 구현(risk-engineer, verifier 확인 전). `test_risk.py`·`test_execution.py`·`test_paper.py`의 설정 픽스처가 모든 `AM_*` 환경 변수를 지우고 `get_settings.cache_clear()` 후 `Settings(_env_file=None)`을 만든다. conftest는 바꾸지 않았다(D-012). 다른 테스트 파일은 여전히 `get_settings()`를 거칠 수 있지만, 실매매 경로를 타는 코드는 이 세 파일만 시험한다.
- 검증: verifier 확인(2026-10-20). `config.py:14-16,43-45`. `tests/`에서 `get_settings`, `_env_file`, `AM_` 참조는 0건이다.

### [ISSUE-015] `adj_close`가 배당을 세전으로 재투자해 원천징수 15%가 빠짐
- 현상: 패널, 타깃, 예측 track record가 `adj_close`를 쓴다(Yahoo `auto_adjust=False`). 배당 종목의 `adj_close/close` 최솟값은 0.61~0.99다(XOM 0.61, SPY 0.824). SPY 단순 보유 기준선을 `adj_close`로 계산하면 실제보다 유리하다. 대략 SPY 배당수익률 약 1.3% × 15% ≈ 연 0.2%p 차이다. 분할로 생긴 가격 점프는 2015년 이후 없다.
- 원인: 한국 거주자는 미국 배당에서 15%를 원천징수당하는데 `adj_close`는 세전 기준이다.
- 근거: demo.db 조회(data A7), `backend/app/forecast/panel.py:88,139`.
- 해결: data 쪽 2단계 wave A(2026-10-21). `app/data/series.total_return_index(close, dividends, withholding)`, `DailyBars.total_return(withholding)`. 실제 캐시 ETF 15종+주식 4종에서 w=0 결과와 adj_close의 최대 상대 차이 1.4e-6. w=15%면 연 0.09~0.69%p 낮다(SPY 0.28%p). 백테스트 적용은 eval 담당. eval 부분(eval 2단계 wave A 구현(2026-10-21, verifier 검증 전)): `run_backtest`는 adj_close를 쓰지 않는다. 배당락일에 (전날 종가 기준 보유 수량 × 주당 배당 × (1 − 15%))를 현금으로 받고 환전 비용을 낸다. 전략과 기준선이 같은 함수를 쓴다(`test_dividends_are_paid_net_of_withholding_on_the_ex_date`).
- 검증: verifier 확인(2026-10-20). adj_close/close 최솟값은 XOM 0.6116, SPY 0.8240, AMZN 1.0이다. 주식 종가의 일간 |log 수익률| 최대는 0.43(NFLX)로, 분할 크기의 점프가 없다. 연 0.2%p는 추정치(산식만 확인).

### [ISSUE-016] 코인을 USD 시세로 백테스트하면 업비트 KRW 손익과 달라짐
- 현상: OOS는 BTC-USD 등 달러 시세 기준이다. 하지만 CLAUDE.md상 업비트·빗썸 코인은 KRW로 거래·평가한다. 그래서 김치 프리미엄 변동과 USD/KRW 변동이 손익에 들어가지 않는다. 업비트 KRW 시계열은 지금 2021-10-20부터 5년치만 받아 둔 상태다.
- 원인: 예측 패널이 Yahoo `*-USD`로 만들어졌다.
- 근거: `backend/app/forecast/universe.py:24-27`, CLAUDE.md 「거래 통화」(quant A7). 의견이 갈린다. quant는 체결 통화(업비트 KRW) 기준 손익을, eval은 USD 시세를 주로 쓰고 KRW로 환산하며 업비트는 민감도로 볼 것을, risk는 수익률 곡선을 KRW 하나로 통일할 것을 제안했다(eval C, risk A10).
- 해결: 결정됨(D-014), 2단계 구현 — 담당: evaluation-engineer(백테스트), data-engineer(업비트 KRW 시계열). 주 기준은 코인 USD 시세 × 거래일 USD/KRW로 계산한 KRW 평가다. 업비트 KRW 시세와 업비트 수수료로 계산한 결과는 2021-10 이후 구간에서 민감도로 함께 보고한다. eval 부분(eval 2단계 wave A 구현(2026-10-21, verifier 검증 전)): `run_backtest`는 KRW로 평가하고, 업비트 KRW 시세·수수료 민감도는 `load_inputs(..., upbit=True)`로 같은 엔진에 넣는다. 예비 기준선 ①(2021-11~2025-10-18): USD×환율 CAGR 17.3%, 업비트 KRW 17.7%.
- 검증: 사실 확인(2026-10-20). `universe.py:24-27`이 모두 `*-USD`다. 보류 결정은 검증 대상이 아니다.

### [ISSUE-017] 기준선 ①(SPY·BTC 단순 보유) 자체가 MDD 20% 한도를 넘음
- 현상: adj_close 기준 고점 대비 최대 하락폭은 다음과 같다.

  | 기준선 | 하락폭(시점) |
  |---|---|
  | SPY | −33.7%(2020-03-23), −24.5%(2021~22년) |
  | BTC | −83.4%(2018-12-15), −76.6%(2021~22년) |

  둘 다 MDD 20% 한도를 넘는다. 따라서 한도를 지키는 전략은 원래 수익률에서 단순 보유에 지는 것이 정상일 수 있다.
- 원인: MDD 20% 한도는 전략에만 걸리고 기준선에는 걸리지 않는다(규칙상 의도된 차이).
- 근거: demo.db adj_close로 계산(VERIFICATION.md 반박·수정 4), CLAUDE.md 「리스크 한도」(eval 추가 관찰, quant A8). 세후·원화 기준 수치는 2단계 백테스트에서 다시 계산한다.
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). `baselines.baseline_1_suite`가 기준선 ①(SPY 0.8 + BTC 0.2, 월 리밸런싱)과 진단용 변형(리밸런싱 없음, SPY 100%, BTC 100%, 변동성 맞춤 k = min(1, σ전략/σ기준선))을 같은 `run_backtest`로 계산한다(D-021). 순 Sharpe 차이와 Deflated Sharpe는 `evaluation.sharpe_test`다. 예비 실데이터 결과(2017-01-01~2025-10-18, KRW, 비용·세금 차감, 마지막 날 전량 매도): 기준선 ① MDD 32.1%, SPY 30.2%, BTC 82.8%로 셋 다 20%를 넘는다(PROGRESS.md 「기준선 ① 예비」). risk-engineer 부분(`adopt_strategy`)은 `adoption_gate`가 그대로 호출한다.
- 검증: verifier 확인, 가설 → 사실(2026-10-20). demo.db Yahoo 일봉 adj_close 기준 SPY MDD −33.7%(2020-03-23), 2021~22년 −24.5%. BTC −83.4%(2018-12-15), 2021~22년 −76.6%. 두 기준선 모두 20%를 넘는다.

### [ISSUE-018] 보정하지 않은 p_up이 자산군마다 다른 방향으로 치우침
- 현상: walk_forward 구간에서 초과 p_up(`gbdt_p_up − climatology_p_up`)의 중앙값은 코인 +0.017/+0.037/+0.060, 주식 −0.007/−0.014/−0.018이다(1d/1w/1m, 결과값 미사용). `q10 > 0`이거나 `q90 < 0`인 행은 0%다. 이 수치는 디스크 run의 `oos_{h}.csv.gz`에서 계산했으므로 보유 종목만 담긴 표본이고(ISSUE-004) 유니버스 전체가 아니다. 전체 OOS를 저장한 뒤 다시 계산한다.
- 원인: p_up에는 확률 보정이 없고 conformal은 q10·q90에만 적용된다. Brier가 climatology보다 나쁜 것과 같은 원인으로 본다(가설).
- 근거: `backend/app/forecast/walkforward.py:42-49`, `oos_{h}.csv.gz` 분포(quant A9).
- 해결: 신호 구현 완료(2026-10-21, `strategy/signals.py`). 재학습 run `20261021T163606-f5e2aae3`의 전체 OOS로 다시 계산했다(walk_forward, 전략 유니버스, 결과값 미사용). 초과 p_up 중앙값은 코인 +0.015/+0.036/+0.062, 주식 −0.007/−0.012/−0.014다(1d/1w/1m). q10>0 또는 q90<0인 행은 여전히 0%다. 치우침은 그대로이므로 자산군 내 순위를 쓰는 설계를 유지한다. 신호는 자산군 안의 상대 순위를 쓴다(S1). 신뢰도는 원래 p_up이 아니라 시점 기준의 과거 적중률로 낸다. 원래 p_up으로 기준값을 잡으면 "코인 매수, 주식 매도"라는 자산군 베팅이 되기 때문이다.
- 검증: 부분 확인(2026-10-20). 중앙값 +0.017/+0.037/+0.060, −0.007/−0.014/−0.018과 'q10>0 또는 q90<0 = 0%'를 재현했다. 다만 이 수치는 보유 종목만 담긴 oos 파일에서 나왔고, 유니버스 전체가 아니다(ISSUE-004). 원인은 가설로 유지한다.

### [ISSUE-019] 1d 신호는 비용과 회전율 때문에 불리함
- 현상: 기대수익 |q50×scale|의 자산군별 중앙값이 1d는 코인 15bp·주식 10bp, 1w는 89bp·54bp, 1m은 388bp·204bp다. 초과 p_up의 1차 자기상관은 1d 0.63, 1w 0.89, 1m 0.93이다. 자기상관은 종목마다 날짜순 lag-1 자기상관을 구한 뒤 종목 평균을 낸 값이고, 종목 중앙값으로는 0.61/0.88/0.94다(evaluation-engineer 재계산). 모두 walk_forward 구간이고, 보유 종목만 담긴 디스크 run의 `oos_{h}.csv.gz`에서 계산했다(ISSUE-004). D-008의 1d 제외 근거도 같은 표본이다. 전체 OOS를 저장한 뒤 다시 확인한다.
- 원인: 1d 예측은 신호 크기가 작고 날마다 크게 바뀐다. 업비트 왕복 수수료(약 10bp)에 스프레드와 슬리피지까지 더하면 1d의 예상 우위가 상쇄된다.
- 근거: `oos_{h}.csv.gz` walk_forward 구간 분포(quant A10).
- 해결: S1은 1w(주)와 1m(보조)만 쓰고 1d는 제외했다(D-008). 재학습 run의 전체 OOS로 다시 계산한 수치(walk_forward, 전략 유니버스, 결과값 미사용)는 다음과 같다(quant, 2026-10-21). |q50×scale| 중앙값은 1d 코인 11.8bp·주식 5.1bp, 1w 77bp·28bp, 1m 353bp·107bp다. 초과 p_up 자기상관(종목별 평균)은 1d 0.62/0.66, 1w 0.92/0.85, 1m 0.94/0.89다. 1w에서 기대수익이 등록 허들(주식 0.80%, 코인 0.60%)을 넘는 행은 주식 4.7%, 코인 59.6%다.
- 검증: 부분 확인(2026-10-20). |q50×scale| 중앙값 15/10, 89/54, 388/204bp를 재현했다. 자기상관도 원 수치(종목별 평균 0.63/0.89/0.93)를 그대로 재현했다(중앙값은 0.61/0.88/0.94). 표본 한계는 ISSUE-018과 같다.

### [ISSUE-020] `LARGE_CAPS` 생존 편향
- 현상: `LARGE_CAPS`는 2026년 기준 대형주를 사후에 고른 목록이다. 예측 학습용으로 묶어 쓰는 것은 괜찮지만, 이 유니버스로 횡단면 전략을 백테스트하면 성과가 과대 추정된다. 주식 IC도 이 유니버스에서 계산됐다.
- 원인: 상장 폐지 종목이 없는 현재 기준 유니버스다(`universe.py` 모듈 설명에 이미 적혀 있음).
- 근거: `backend/app/forecast/universe.py:7-10,19-23`(quant A11).
- 해결: 미해결 — 2단계 담당: evaluation-engineer(전략 유니버스는 지수·섹터 ETF와 코인 4종으로 하고, 대형주 결과는 참고용으로 따로 보고, D-008), quant-researcher(신호 대상 유니버스 반영). quant 부분 완료(2026-10-21): `universe.strategy_symbols()`가 S1 유니버스이고, 대형주는 `s1.large_cap_reference`로 따로 돌린다. eval 부분(eval 2단계 wave A 구현(2026-10-21, verifier 검증 전)): 순위 edge 검정(`compare_all`, `PointInTimeEdge`)은 `rank_symbols=universe.strategy_symbols()`만 쓴다. 대형주 결과는 판정에 들어가지 않는다(D-018).
- 검증: verifier 확인(2026-10-20). `universe.py:7-10,19-23`.

### [ISSUE-021] 공급자 경계에서 OHLC를 검증하지 않음
- 현상:
  - `^VIX` 2026-10-19 봉은 open/high/low가 0인데 그대로 저장돼 있다.
  - `KRW=X`는 3,071봉 중 274봉에서 종가가 [저가, 고가] 범위를 벗어난다(중앙값 0.07%, 최대 1.47%, 2023-12-18).
  - `KRW=X`의 고가/저가 비율이 5%를 넘는 날이 6일이다(최대 11.25%, 2025-11-28).
- 원인: 공급자가 종가 NaN만 거른다.
- 근거: `backend/app/data/yfinance_provider.py:37`(data A4).
- 해결: 2단계 wave A(data, 2026-10-21, D-017). 모든 공급자 응답에 `quality.validate_bars` 적용: 종가·수정 종가가 없거나 0 이하면 버림, 시가·고가·저가가 깨진 봉은 남기고 경고 로그와 `ohlc_ok=False`, 범위 밖 종가는 품질 보고서에서만 셈. FX·지수의 고가·저가는 쓰지 않는다. 재수집 후 깨진 봉은 ICP-USD 2021-05-10 1개(^VIX 10-19는 Yahoo가 고쳐서 정상).
- 검증: verifier 확인(2026-10-20). `^VIX` 10-19 open/high/low/volume이 0이다. KRW=X 범위 밖 종가 274봉(최대 1.47% 2023-12-18, 중앙값 0.07%), 고가/저가 5% 초과 6일(최대 11.25% 2025-11-28). `yfinance_provider.py:37`.

### [ISSUE-022] 실패나 결측을 조용히 다른 값으로 대체하는 경로
- 현상: FakeProvider와 FakeExtractor는 설정값으로만 선택되고, 실제 실행에서 Fake로 넘어가는 경로는 없다. 다만 다음과 같은 경로가 있다.
  - `usd_krw_lookup`: 환율 봉이 없으면 모든 과거 날짜에 오늘 환율을 쓰고, 첫 봉보다 이른 날짜에는 첫 봉 환율을 쓴다. 확정 봉 필터도 없다.
  - `services/forecasts.py:283`: 환율 대체 경로가 `final_only` 없이 시세를 읽는다.
  - `forecast/data.py`: 오류가 나거나 봉이 300개 미만이면 경고만 남기고 제외한다. SPY나 BTC-USD가 빠지면 beta 피처가 NaN이 된 채 학습이 진행된다.
- 원인: 기능 저하를 허용하는 설계다. 또 "빈 응답에도 `synced_at`이 갱신된다"는 확인됐다(verifier 재현). 기존 sync가 있고 TTL이 지난 상태에서 공급자가 빈 목록을 주면 `synced_at`이 앞으로 간다(verifier `scratchpad\verifier\empty_refresh.py`, V-2). 그래서 갱신이 실패해도 캐시가 "최신"으로 표시되고, ISSUE-001과 겹치면 미완성 봉의 수명이 늘어난다. 남은 가설은 yfinance가 레이트 리밋이나 일시 오류 때 실제로 예외 대신 빈 DataFrame을 돌려주는가 하나다.
- 근거: `backend/app/services/market_data.py:140-152`, `backend/app/services/forecasts.py:281-284`, `backend/app/forecast/data.py:62-70`, `market_data.py:155` 이하 `_sync`(data A5).
- 해결: data 쪽 2단계 wave A(2026-10-21). 빈 응답이면 `synced_at`을 갱신하지 않음(테스트 `test_empty_refresh_does_not_advance_synced_at`). `usd_krw_lookup(start, strict=True)`. 엄격 로더 `app.forecast.data.load_daily`·`load_usd_krw`는 결측·오래된 값·공급자 실패를 `DataUnavailableError`로 멈춘다. `load_inputs`는 SPY·BTC-USD와 CONTEXT 종목이 없으면 예외. `forecasts.py:283`은 app-engineer 담당으로 남음(D-011).
- 검증: verifier 확인(2026-10-20). 세 경로를 코드로 확인했다. 가설 중 '빈 응답이어도 `synced_at`이 갱신된다'는 코드 경로(`market_data.py:177-221`)와 재현(`scratchpad\verifier\empty_refresh.py`)으로 확인했다. yfinance가 레이트 리밋 때 빈 DataFrame을 주는지는 미확인이다.

### [ISSUE-023] 환율 공백과 자산 간 달력 정렬
- 현상: `KRW=X`는 평일만 있다(주말 0개). 평일 결측 8일(예: 2025-01-01, 2017-07-11, 2019-05-22), 최장 공백 5일(2025-04-17 → 04-22), 전일과 종가가 같은 날 17일이 있다. 2% 넘게 움직인 날이 15일 있다(예: 2016-06-27, 2022-12-01 −3.5%). 이 날들이 실제 사건일인지는 대조한 근거가 없다(미확인). `^VIX`는 미국 휴장일(2026-05-25, 09-07)에 봉이 있고, `DX-Y.NYB`는 휴장일 봉이 3개다.
- 원인: Yahoo의 FX·ICE 일정이 NYSE 달력과 다르다. 휴장일 봉과 주말 공백은 데이터 오류가 아니다. 2% 초과 변동일이 실제 변동인지 데이터 오류인지는 확인하지 않았다.
- 근거: demo.db 조회, `scratchpad\quality.py`(data A6), `backend/app/services/market_data.py:140-152`(forward-fill 상한 없음).
- 해결: 2단계 wave A(data, 2026-10-21). `app/data/series.align_daily`(행 D = D+1 00:00 UTC, forward-fill 상한, `age_days`), `load_usd_krw`(상한 5일). FRED DEXKOUS(뉴욕 정오 고시)와 대조: Yahoo 2% 초과 15일 중 7일은 FRED도 같은 방향으로 1% 넘게 움직였다(2016-06-27, 2016-11-10, 2020-03-25, 2022-11-14, 2022-12-01, 2025-04-10, 2025-05-05). 나머지 8일은 FRED에 대응하는 움직임이 없다(가설: Yahoo 종가 시각·호가 오류). 두 출처 수준 차이는 중앙값 −0.08%, |차이| 99분위 1.5%. Yahoo 평일 결측 8일 중 5일은 FRED에 값이 있다.
- 검증: 부분 확인(2026-10-20). 평일 결측 8일, 최장 공백 5일(2025-04-17→04-22), 2% 초과 15일, VIX 휴장일 봉 2개, DXY 휴장일 봉 3개를 확인했다. '15일 모두 실제 사건일과 일치'는 근거가 없다.

### [ISSUE-024] `^VIX`·`^VIX3M`·`^TNX` 종가가 장 마감 뒤 값일 수 있음(가설)
- 현상: 주식 행은 이 지표들을 지연 0일로 본다. Yahoo의 VIX 종가가 16:15 ET 값이라면, 장 마감 뒤 15분 정보를 쓰는 셈이다.
- 원인: 가설, 확인 필요.
- 근거: `backend/app/forecast/universe.py:41-48`(quant A6).
- 해결: 미해결 — 2단계 담당: data-engineer(종가 시각 확인), quant-researcher(장 마감 뒤라면 지연을 1로 바꾸고 재학습 설정에 포함). quant 부분 완료(2026-10-21): 종가 시각이 확인되지 않아 보수적으로 주식 행의 VIX·VIX3M·TNX(와 vix_term) 지연을 1로 바꿨다. 설정 3에 포함된다. 백테스트가 다음 봉 시가에 체결하므로 체결 측면의 영향은 없다(D-008).
- 검증: 미확인, 가설 유지(2026-10-20). 코드상 지연 0만 확인했다(`universe.py:41-42,48`). 종가 시각은 확인하지 않았다.

### [ISSUE-025] 실제 DB 시세 캐시가 사실상 비어 있음
- 현상: `asset_manager.db`에는 일부 종목만 캐시돼 있고, SPY, BTC-USD, KRW=X, 유니버스 시세가 없다. 유니버스 전체는 `demo.db`에만 있다(Yahoo 실데이터, BTC 2021-11-08 종가 67,566으로 확인).
- 원인: 가설. 지금까지 학습이 다른 DB 파일을 대상으로 실행된 것으로 보인다.
- 근거: 실제 DB 읽기 전용 조회(data A9, eval도 같은 결과 확인).
- 해결: 2단계 wave A(data, 2026-10-21). 실제 DB의 `symbol_syncs`를 지우고 77종을 다시 받았다(유니버스 68종 + CONTEXT 4종 + KRW=X + 업비트 4종, 2015-01-01부터, 실패 0). price_bars·symbol_syncs에만 썼다. 결측은 AVAX 70일, 업비트 KRW-ETH·XRP 2017-10-21~23, DX-Y.NYB 2일, ^TNX 1일, KRW=X 평일 8일, 그리고 Yahoo 코인 전부 10-20(ISSUE-010).
- 검증: verifier 확인(2026-10-20). 실제 DB(symbol_syncs·price_bars만 열람)에는 SPY/BTC-USD/KRW=X가 0봉이고 유니버스 시세도 없다. demo.db에는 유니버스 전체가 있고 BTC 2021-11-08 종가는 67,566.83이다. demo.db 10-16~10-18 BTC 종가는 지금 Yahoo 응답과 같다.

### [ISSUE-026] `.gitignore`가 `.claude` 전체를 무시해 역할 정의가 커밋되지 않음
- 현상: `.gitignore` 마지막 줄의 `.claude` 규칙이 디렉터리 전체를 무시해서 `.claude/agents/*.md`가 추적되지 않는다. 새로 클론하면 역할 정의가 없다. 파일 끝에 줄바꿈도 없어서 `>>`로 규칙을 덧붙이면 두 규칙이 한 줄로 붙어 모두 깨진다. 민감 파일(`*.db`, `.env`, `backend/artifacts/`)은 잘 막혀 있고 기록에도 없다.
- 원인: c8216b6에서 "Claude Code 개인·임시 파일" 규칙으로 추가됐다.
- 근거: `git check-ignore -v .claude/agents/risk-engineer.md` → `.gitignore:38:.claude`, `tail -c` 확인 결과 마지막 바이트가 `e`(risk A8).
- 해결: 보류(`.gitignore`는 담당자가 없고, 커밋 여부는 사용자가 판단할 일이다. TODO_FOR_ME.md에 등록했다). 제안: `.claude/*` + `!.claude/agents/`로 바꾸고 마지막에 줄바꿈을 넣는다.
- 검증: verifier 확인(2026-10-20). `git check-ignore` → `.gitignore:38:.claude`, 마지막 바이트 'e', `git ls-files .claude` 0건. `docs/dev/`는 무시되지 않아 커밋 시 공개된다.

### [ISSUE-027] `str(exc)`를 응답에 그대로 내보내는 패턴(향후 키 유출 경로, 가설)
- 현상: 두 API 키는 `SecretStr`이고 Finnhub 키는 헤더로 보내므로 지금 유출 경로는 없다. 다만 `str(exc)`를 응답이나 작업 상태로 그대로 보내는 곳이 있다. 나중에 업비트 주문 API(access/secret 키, JWT)를 붙이면 같은 패턴으로 키나 계좌 정보가 흘러나갈 수 있다.
- 원인: 가설(앞으로의 위험). 지금 해당 요청에는 비밀값이 없다.
- 근거: `backend/app/data/upbit_provider.py:73`, `backend/app/data/yfinance_provider.py:53,60,77`, `backend/app/services/news.py:158`, `backend/app/services/forecasts.py:431`, `backend/app/services/predictions.py:147`, `backend/app/main.py:54-58`(risk A7).
- 해결: risk-engineer 몫은 2단계 wave A에 구현(verifier 확인 전). `execution.execute`는 브로커 예외를 고정 문구("주문 전송 실패", "실매매 브로커가 없음")로 바꾸고 로그에는 예외 타입만 남긴다. `paper.py`도 데이터 오류를 고정 문구(`RunReport.skipped`, 킬스위치 `detail`)와 예외 타입 로그로만 남겨, 엄격 로더의 예외 문구(공급자 `str(exc)` 포함)가 기록에 들어가지 않는다. 테스트: `test_execution.py::test_broker_errors_never_leak_secrets`(가짜 키·계좌번호를 심은 예외 → 결과·로그에 없음), `test_paper.py::test_unpriced_account_trips_stale_data`, `test_missing_inference_data_records_no_signal_and_sends_nothing`. 브로커 키 설정 항목은 실매매를 구현할 때까지 만들지 않는다. data-engineer 몫(공급자 예외 문구)은 미해결.
- 검증: verifier 확인(2026-10-20). 인용한 줄이 모두 `{exc}`/`str(exc)`를 응답이나 작업 상태로 보낸다. 키는 `SecretStr`(`config.py:27,34`)이다.

### [ISSUE-028] 홀드아웃 fold는 1년 내내 재학습하지 않음
- 현상: 표본 기간 fold는 91일마다 재학습하는데, 홀드아웃은 시작 시점 모델 하나로 365일을 예측한다. 운영(분기 재학습)과 조건이 다르다.
- 원인: `walk_forward`가 홀드아웃을 fold 하나로 처리한다(보수적 설계).
- 근거: `backend/app/forecast/cv.py:49-52`, `backend/app/forecast/walkforward.py:108`(eval E-7).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). 바꾸지 않기로 했다(D-019). 홀드아웃은 시작 시점 모델 하나로 예측한다. 운영보다 보수적이고, 홀드아웃이 참고용(D-015 ②)이 되었기 때문이다. 예측 report 수치는 바뀌지 않는다.
- 검증: verifier 확인(2026-10-20). `walkforward.py:108`, `cv.py:49-52`.

### [ISSUE-029] 표본 기간 마지막 fold의 라벨이 홀드아웃 구간 가격을 사용
- 현상: 표본 기간 마지막 fold는 홀드아웃 시작일 직전까지 이어진다. 그 끝부분 행의 목표값은 최대 32일 동안 홀드아웃 가격을 본다. 영향은 표본 기간 점수에만 있다. 학습과 conformal 보정 구간은 퍼지되어 있다.
- 원인: `folds()`가 홀드아웃 앞에 퍼지 간격을 두지 않는다(코드로 확인).
- 근거: `backend/app/forecast/cv.py:44-47`, `backend/app/forecast/walkforward.py:52-57`, `backend/tests/test_forecast.py:109-120`(학습 쪽만 검사, eval E-8).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). `PurgedWalkForward.folds`의 마지막 테스트 블록이 `holdout_start − (horizon_days + embargo_days)`에서 끝난다(`walk_forward_end`). verifier B-1 이후 퍼지 폭 전체를 빼도록 바꿨다. 주식 21세션은 최대 35일에 걸치기 때문이다. 그래서 walk_forward 목표값이 홀드아웃 가격을 쓰지 않는다. 테스트는 `test_walk_forward_targets_stop_before_the_holdout`. 다음 재학습(설정 3)부터 walk_forward 행이 기간별로 4~32일 줄어든다.
- 검증: verifier 확인(2026-10-20). `cv.py:44-47`의 마지막 fold `test_end`가 `holdout_start`이고 퍼지가 없다. 학습(`train_end = start - gap`)과 보정(`walkforward.py:52-57`)은 퍼지된다.

### [ISSUE-030] "backtest"라는 이름이 예측 OOS와 전략 백테스트에 겹침
- 현상: 기존 `Run.backtest`, `ForecastService.backtest`는 예측 OOS를 화면에 보여 주는 용도다. 새 `strategy/backtest.py`와 헷갈린다.
- 원인: 이름을 먼저 쓴 쪽이 예측 화면이다.
- 근거: `backend/app/forecast/store.py:34-38`, `backend/app/services/forecasts.py:370-387`(eval E-9).
- 해결: 보류(서비스·API 이름은 app-engineer 담당이고, 이번 단계에는 app-engineer를 투입하지 않는다, D-010). 그 사이 전략 쪽은 `run_backtest`라는 이름으로 구분한다.
- 검증: 사실 확인(2026-10-20). `store.py:34-38`, `forecasts.py:370-387`.

### [ISSUE-031] 연도별 일관성이 부분 연도를 한 해로 셈
- 현상: 몇 달뿐인 첫 해나 홀드아웃 직전 해도 다른 해와 같은 가중치로 센다.
- 원인: `groupby(year).mean()` 뒤 부호 비율을 낸다.
- 근거: `backend/app/forecast/report.py:96-97`(eval E-12).
- 해결: eval 2단계 wave A 구현(2026-10-21, verifier 검증 전). `metrics.year_share`는 그해 관측의 첫날~마지막 날이 182일 미만인 해를 뺀다. report 비교, 시점 기준 edge, 전략 연도 일관성에 모두 쓴다. 평가 변경이라 설정 3 report부터 적용한다(D-018). 테스트는 `test_year_share_leaves_out_partial_years`.
- 검증: verifier 확인(2026-10-20). `report.py:96-97`.

### [ISSUE-032] 셸에 `VIRTUAL_ENV`가 잡혀 있으면 `py -m uv`가 실패함
- 현상: `py -m uv run pytest`가 `backend\.venv\Scripts\python.exe: No module named uv`로 실패한다.
- 원인: 셸에 `VIRTUAL_ENV=backend\.venv`가 잡혀 있으면 `py`가 venv의 파이썬을 고른다(`py -0p`에서 `*` 표시로 확인).
- 근거: 실행 오류, `py -0p` 출력(eval E-11).
- 해결: 보류(사용자 환경 문제라 TODO_FOR_ME.md에 등록). `py -3.11 -m uv ...`를 쓰거나 `VIRTUAL_ENV`를 해제한다. CLAUDE.md 명령 절에 한 줄 추가할지는 리드가 판단한다.
- 검증: verifier 확인(2026-10-20). `py -m uv --version` → `No module named uv`, `py -0p`의 `*`가 `backend\.venv`다. `py -3.11 -m uv`로 우회해 모든 검증을 실행했다.

### [ISSUE-033] 문서·규칙 불일치(자리표시자, 추출기 기본값, 기록 폴더)
- 현상:
  - CLAUDE.md의 `Kaggle [대회명]`, `MDD [20]%`가 자리표시자 그대로다.
  - CLAUDE.md는 스크린샷 추출기를 Claude 기준으로 설명하지만, 실제 기본값은 `import_extractor="ollama"`다.
  - `docs/dev/`와 `backend/app/strategy/`가 없었다.
- 원인: 팀 규칙이 새로 추가됐다.
- 근거: `backend/app/config.py:31`, CLAUDE.md 「매매 신호·전략 규칙」(data A10, quant A12, risk A9, eval E-10).
- 해결: 미해결 — 2단계 담당: 리드. `docs/dev/`는 1단계 문서화로 만들었다(STRATEGIES.md는 quant-researcher가 2단계에 작성). 자리표시자는 D-001·D-002로 운영하면서 사용자 확정을 기다린다(TODO_FOR_ME.md). 추출기 설명은 리드가 CLAUDE.md를 갱신할 때 맞춘다.
- 검증: verifier 확인(2026-10-20). `config.py:31` 기본값 `ollama`, CLAUDE.md 자리표시자 두 곳.

### [ISSUE-034] 백테스트 킬스위치 참고 집계가 연말 세금 납부를 일일 손실로 셈
- 현상: S2-1d 백테스트(데모 자본 1억원 기준)의 킬스위치 참고 발동 1회(2024-12-31)는 그날 평가액이 −3.06% 줄어서 생겼다. 그중 약 −2.80%p는 그날 낸 2024년 양도세(약 350만원)이고, 시장 움직임은 약 −0.26%였다. d2의 2025-10-18 발동도 마지막 날 매도·세금 정산일과 겹친다. 기준선의 발동 횟수에도 같은 경우가 섞여 있을 수 있다(가설).
- 원인: `summarize`가 세금을 낸 뒤의 평가액 곡선으로 `kill_switch_triggers`를 계산한다. 세금 납부일의 평가액 감소가 일일 손실 3%로 잡힌다.
- 근거: verifier 재현 `scratchpad\verifier\s2_killswitch_check.py`. 평가액은 2024-12-30 125,082,105원에서 2024-12-31 121,253,775원으로 줄었고, `tax_by_year[2024]`는 3,505,083원이다. 코드는 `backend/app/strategy/backtest.py`의 `settle_taxes`(12-31 납부)와 `summarize`의 `kill_switch_triggers(eq, ...)`.
- 해결: 판정에는 영향이 없다. 채택 판정은 킬스위치를 끈 MDD로 하고(D-003), 발동 날짜는 참고용이다. 리드 결정으로 risk 방식을 채택했다(2026-10-22, 최종 해결). 백테스트와 모의투자가 같은 킬스위치 규칙을 쓴다(D-003).
  - risk: `risk.kill_switch_triggers(..., flows=)`와 `portfolio_breach(..., flows=)`. 일일 손실 규칙에서 그날 계좌 밖으로 나가거나 들어온 돈(세금, 입출금)을 뺀다. 낙폭 규칙은 세금을 낸 곡선 그대로 센다. flows를 넘기지 않으면 이전과 같다.
    - 일일 손실을 시장 손익으로 센 이유: 일일 손실 킬스위치는 하루짜리 이상 손실을 잡는 장치다. 연말 세금 납부로 운영이 매년 멈추면 오탐이다.
    - 낙폭은 세금을 포함한 이유: 세금은 실제 비용이고, 채택 MDD도 같은 세후 곡선으로 잰다(D-003, 백테스트와 운영의 규칙 일치). 입출금이 생기면 낙폭도 그만큼 보정해야 한다. 지금은 모의투자와 백테스트 모두 입출금이 없어 해당하지 않는다.
    - 모의투자(`paper.py`)는 세금·입출금을 모형화하지 않는다. 그래서 운영 킬스위치는 이 이슈의 영향을 받지 않았고, flows도 넘기지 않는다.
  - eval:
    - `run_backtest`가 날짜별 세금 납부액을 `BacktestResult.tax_paid`에 남긴다.
    - `summarize`가 `flows=-tax_paid`로 넘긴다.
    - 세금 납부일·청산일의 발동(이제 낙폭 규칙만 해당)은 `kill_switch_on_settlement_days`로 따로 표시한다.
    - 판정과 성과 수치는 바뀌지 않는다. 채택 MDD는 `max_drawdown`(세후 곡선)으로 계산하고 킬스위치를 쓰지 않는다. 테스트는 `summarize`에서 킬스위치 항목을 뺀 모든 값이 flows 유무와 무관하게 같은지 확인한다.
  - 영향: 이전 보고(wave A·B, wave C)의 `kill_switch_count`는 수정 전 방식으로 센 값이다. S2-1d의 1회(2024-12-31)는 새 방식에서 0회다. 기준선 횟수는 다시 계산하지 않았다(참고값).
- 검증: verifier 재현(2026-10-22). 세금을 빼면 그날 손실은 3% 한도 아래다. eval 테스트 `tests/test_backtest.py::test_kill_switch_daily_loss_leaves_out_taxes_paid`: 곡선이 3% 넘게 떨어진 세금 납부일이 발동으로 세지 않는다.
  - risk 테스트(`tests/test_risk.py`):
    - `test_daily_loss_leaves_out_taxes_and_other_cash_flows`
      - 이 이슈 수치는 flows가 없으면 발동하고, 세금을 flows로 넘기면 발동하지 않는다.
      - 같은 날 시장 −4%는 세금이 있어도 발동한다.
      - 입금은 손실을 가리지 않는다.
    - `test_drawdown_still_counts_taxes_paid`
  - 전체 405개가 통과했다. verifier 재확인 완료(2026-10-22): `_daily_loss`는 1 − (오늘 − flow)/어제이고 summarize가 flow = −세금을 넘기므로 세금이 더해져 손실에서 빠진다. 이 이슈 수치로 계산하면 (121,253,775 + 3,505,083) / 125,082,105 → 손실 0.26%라 발동하지 않는다. 낙폭 규칙과 채택 MDD는 세금을 낸 곡선 그대로다. 운영 킬스위치(`paper.py`의 `kill_switch_triggers`·`portfolio_breach` 호출)에는 flows를 넘기지 않아 동작이 바뀌지 않는다(fail-closed 유지). S2의 낙폭은 10.7%라 새 방식에서 발동은 0회가 맞다.

### [ISSUE-035] 유명 투자자 데이터 출처의 품질 문제(ARK 펀드 파일 갱신 중단, SEC User-Agent, 13F 중복 행)
- 현상(2026-10-22 확인):
  - ARK 보유 CSV(`assets.ark-funds.com/fund-documents/funds-etf-csv/`) 6개 중 ARKF·ARKX는 `Last-Modified` 2026-01-02, ARKW는 2026-10-06에서 멈춰 있다. ARKK·ARKG·ARKQ는 당일(10/22) 자료다. 펀드 페이지가 쓰는 `/api/fund/holdings/{id}`는 HTTP 500(HTML)을 돌려줘 대안이 없다. 예전 `ark-funds.com/wp-content/uploads/...` 경로는 301 → 404.
  - SEC EDGAR는 User-Agent가 `"asset-manager-dev (local test)"`처럼 연락처가 없으면 "Undeclared Automated Tool" 페이지로 거부한다. `앱이름 이메일` 형식이면 통과한다.
  - 13F 정보표는 같은 종목이 보고 주체(자회사·공동 운용자)별로 반복된다(Berkshire 2026-06-30: 89행 중 Apple 12행). 수정 보고서 `13F-HR/A`는 `amendmentType`이 `NEW HOLDINGS`(비공개였던 종목 추가)인 경우가 있어 원본을 대체하면 안 된다(Berkshire 2025-08-14, Pershing 2025-04-16 모두 NEW HOLDINGS).
  - Scion(마이클 버리)의 마지막 13F-HR은 2025-11-03 제출(2025-09-30 기준)이고 이후 제출이 없다. Appaloosa는 CIK가 둘인데 `0001006438`(APPALOOSA MANAGEMENT LP)은 2016년 이후 제출이 없고 `0001656456`(Appaloosa LP)이 현재 제출자다.
  - ARK 티커 열에 Bloomberg 거래소 접미가 붙는 행이 있다(`RKLB UQ`, `DKNG UW`). 현금·사모(OpenAI, Kalshi)·워런트 행은 티커가 비어 있고 CUSIP 자리에 내부 코드(`X9USDGSFT`, `PPOPENAIC`)가 있다. OpenFIGI는 이런 값과 SEDOL(`B3Z5T14`)에 `Invalid idValue format`, 케이맨 CINS(`G6683N103`, NU)에 `No identifier found`를 돌려준다.
- 원인: 출처 측 사정(ARK의 파일 발행 중단, SEC 접근 정책, 13F 서식 구조). 앱 코드 문제가 아니다.
- 근거: `curl -D -`로 받은 응답 헤더와 본문, `data.sec.gov/submissions/CIK*.json`, 각 제출의 `primary_doc.xml`(`backend/app/data/guru_provider.py` 모듈 docstring에 요약).
- 해결(`guru_provider.py`):
  - 가장 최신 펀드 파일보다 7일 넘게 오래된 펀드는 합산에서 빼고 스냅샷 `note`에 펀드와 날짜를 적는다(`ARK_MAX_FUND_LAG`). 1월 보유를 오늘 보유로 보여 주지 않기 위함. 한 펀드라도 HTTP 실패면 전체를 실패로 두고 이전 데이터를 유지한다.
  - 13F 행은 CUSIP 기준으로 합산하고 `putCall`(옵션)·`PRN`(채권 원금) 행은 뺀다. `13F-HR/A`는 `amendmentType`을 읽어 `NEW HOLDINGS`면 원본에 더하고 `RESTATEMENT`면 교체한다. 2023-01-03 이전 제출은 천 달러 단위로 환산한다.
  - User-Agent는 `AM_SEC_USER_AGENT`로 사용자가 채운다(TODO_FOR_ME.md). 비어 있으면 13F 투자자는 동기화하지 않고 사유를 표시한다.
  - ARK 티커는 첫 토큰만 쓰고, 티커가 없는 행은 `symbol=None`으로 둔다. OpenFIGI 실패·미발견은 `cusip_tickers`에 `symbol=None`으로 적고 30일 뒤 재시도한다.
- 검증: `tests/test_gurus.py`(고정 CSV/XML 표본, 네트워크 없음). 실제 네트워크 수동 시험 결과는 PROGRESS 보고에 기록. verifier 확인(2026-10-23 백엔드 검증 섹션): 실제 `GET /api/gurus`에서 갱신 중단 ARK 펀드 제외 note와 13F 6명의 `AM_SEC_USER_AGENT 미설정` 사유를 확인.

### [ISSUE-036] 스크린샷 가져오기가 수익률을 평균단가로 읽어도 미리보기가 `ok`로 통과시킴
- 현상: 증권사 앱(토스증권형) 보유 목록 스크린샷을 가져왔을 때 미국 주식 여러 종목의 `avg_price_usd`가 실제 현재가의 수십~수백분의 1 수준으로 인식됐다. 이 화면에는 평균단가가 없고, 종목마다 둘째 줄에 평가손익(원)과 수익률(%)만 있다. 저장된 "단가"는 수익률(예 −7.89%)의 절댓값(7.89)이 그대로 달러 단가로 들어간 값이었다(전 종목 손실 중). 미리보기는 모두 `ok`였고, 그대로 확정되어 장부의 투자원금이 실제의 수십 분의 1로 기록되고 수익률이 수백~수만 %로 표시됐다.
- 원인:
  - 추출 프롬프트가 "per-unit average purchase price in USD" 한 줄만 요구했고, 평균단가가 없는 목록 화면이 있다는 것, 수익률·평가손익·평가금액과 구분하라는 것을 말하지 않았다. 모델이 유일하게 보이는 소수 둘째 자리 숫자(수익률)를 단가 자리에 넣었다.
  - 미리보기 단가 검사가 두 가지뿐이었다. ① `PRICE_SANITY=(0.001, 1000)` 밴드는 장기 보유 승자(0.005배)까지 허용해야 해서 이런 값은 모두 통과한다. ② `_misread_price`는 원화 금액·원화 총액·보유 총액을 단가로 읽은 경우(비율이 환율·수량의 0.8~1.25배)만 잡는다. 수익률을 단가로 읽으면 어느 규칙에도 걸리지 않았다.
  - 추출 스키마에 평가금액·평가손익이 없어 서비스가 매입금액을 역산할 길이 없었다.
- 근거: `backend/app/services/statement_import.py:23`(`PRICE_SANITY`), `_misread_price`(후보 3개), 이전 `backend/app/services/screenshot_extractor.py` `SYSTEM_PROMPT`(단가 설명 한 줄). 프론트엔드 보유 목록은 이미 20배 규칙(`frontend/src/lib/holdings.ts` `SUSPICIOUS_COST_RATIO`)으로 같은 행을 의심 표시하지만, 가져오기 미리보기에는 그 기준이 없었다.
- 해결(2026-10-22, data-engineer):
  - 추출 스키마 `ExtractedHolding`에 `market_value_krw`(평가금액), `pnl_krw`(평가손익, 부호 포함), `return_pct`(수익률, 부호 포함) 추가. 셋은 장부에 쓰지 않고 검증·역산에만 쓴다. 시스템 프롬프트에 한국 증권사 앱(키움·토스·삼성·미래에셋·NH·KB·한투·신한) 보유 행의 열 순서와 뜻, "토스·키움 등 목록 화면에는 평균단가가 없을 수 있다. 없으면 avg_price를 null로 두고 평가금액·평가손익·수익률을 부호째 그대로 적어라. 수익률(%)을 단가로 쓰지 마라", `avg_price_usd`는 한 주당 매수가만이고 수익률·평가손익·평가금액·매입금액·비중·현재가가 아니라는 것, 달러 단가는 현재가와 자릿수가 비슷해야 하고 %·± 기호가 붙은 수는 단가가 아니라는 것, 모르면 `null`+`confidence=low`를 명시했다.
  - 서비스(`statement_import.py` `_row`): 매입금액이 화면에 없으면 `평가금액 − 평가손익`, 없으면 `평가금액 / (1 + 수익률/100)`, 그것도 없으면 `평가손익 / (수익률/100)`으로 `cost_krw`를 역산한다(`_derive_cost_krw`). 부호는 `_signed_decimal`이 `-`·`−`(U+2212)·`–`·`▼`를 음수로 읽는다. 단가(`cost_avg`)는 `cost_krw / 수량 / 오늘 환율`(원화 코인은 환율 없이)이다.
  - 화면의 단가가 없으면 `cost_avg`를 넣고 `price_estimated=True`, `message`="화면에 평균단가가 없어 {평가금액과 평가손익으로} 계산한 단가입니다(오늘 환율 기준)". `status`는 `ok`.
  - 화면의 단가가 있으면 먼저 의심 여부를 본다(`_price_doubt`): 수익률과 ±2% 안이면 "수익률", 현재가와 20배 이상 차이(`SUSPICIOUS_RATIO`, 프론트와 같은 기준)면 "다른 숫자". 그 다음 역산 단가와 비교한다(`_cost_agrees`). 달러 행은 역산 단가/화면 단가 비가 오늘 환율 기준 ±50% 안이면 일치(`FX_DRIFT_TOLERANCE`), 원화 행은 ±5%(`DERIVED_PRICE_TOLERANCE`).
    - 일치하면 의심을 지우고 화면 단가를 그대로 쓴다(매입금액이 뒷받침하는 100배 승자는 진짜다).
    - 의심 + 불일치면 화면 단가를 버리고 `cost_avg`를 넣는다. `price_estimated=True`, `message`="화면의 단가 $7.89은 수익률로 보여 쓰지 않고, 평가금액과 평가손익으로 계산한 단가를 넣었습니다(오늘 환율 기준)".
    - 의심 없음 + 불일치면 값은 두고 `warning`="평균단가 $X이 평가금액과 평가손익으로 계산한 단가 $Y과 N% 다릅니다. 둘 중 하나를 잘못 읽었을 수 있으니 확인하세요".
    - 의심 + 역산 불가(평가금액·손익도 없음)면 값은 두고 `warning`(20배 문구 또는 수익률 문구). 사용자가 단가를 고쳐 가져올 수 있게 `status`는 `ok`.
  - 리드 지시의 "±5%"를 달러 행에 그대로 쓰지 않은 이유: 원화 평가손익은 환차손익을 포함하므로 올바른 달러 단가와 원화 매입금액에서 역산한 단가는 매수 당시 환율/오늘 환율만큼 다르다(최근 몇 년 사이 매수면 10~25%). ±5%면 정상 행이 대부분 경고를 받는다. 1998년 이후 환율이 약 900~1,600원 사이였으므로 ±50%면 정상 쌍은 항상 안에, 다른 열을 읽은 값은 10배 이상 밖에 있다. 원화 행은 환율이 없어 ±5%를 그대로 쓴다.
  - 기존 `invalid` 경로(`_misread_price`의 원화·총액 오독, `PRICE_SANITY` 밖)는 그대로 유지하고, `invalid` 행의 `warning`은 항상 None이다. `PreviewRow`·`PreviewRowOut`에 `warning: str | None` 추가.
  - 프론트엔드(app-engineer 담당): `Import.tsx`에서 `ok` 행에도 `message`(역산 안내)와 `warning`을 표시하고, `warning`이 있는 행은 기본 미선택으로 둔다(`Import.tsx:33`의 `include` 조건, 현재 325행은 `status !== 'ok'`일 때만 message를 보여 준다). `npm run gen:api`로 `schema.d.ts` 재생성.
- 검증: `tests/test_imports.py` 통과 — 토스형 샘플(평균단가 없음, 평가금액·평가손익·수익률만 → `price_estimated` + 역산 매입금액·단가 일치, 수익률만·손익과 수익률만의 두 공식, 수량 없으면 invalid), 수익률 절댓값이 단가에 들어간 실제 사례 재현(평가금액·손익이 있으면 교정, 없으면 경고), 매입금액이 뒷받침하는 28배 승자는 경고 없음, 20배 경고, 수익률 오독 경고, 불일치 경고(값 유지), 기존 invalid 두 경로 유지, 정상 행·0.3배 손실 행은 `warning` None, 부호 파서. 백엔드 전체 pytest·`ruff check`·`ruff format --check` 통과. 프롬프트 변경은 실제 스크린샷으로 재시험이 필요하다(TODO: 사용자가 같은 스크린샷을 다시 올려 미리보기에서 역산 단가가 들어오는지 확인). verifier 확인 대기.

### [ISSUE-037] 범위 예측의 `range_reason`이 검증 결과와 무관하게 `forward_test_pending`이라 화면이 "과거 검증 통과"로 과장함
- 현상: `GET /api/forecasts/{symbol}`의 1d·1w·1m `range_reason`이 모두 `forward_test_pending`이다. 그런데 현재 run report의 `stock:range` edge는 1d만 True이고 1w·1m은 False(보정 p 1.0)다. 종목 상세 「앞으로 예상」의 배지는 1w 기준이라 `실전 검증 대기`가 뜨고, 옆 문장은 "과거 검증은 통과했지만 실전 확인이 끝나지 않았어요"라고 적는다. 접기 안 `Verdicts`도 1w·1m 범위를 "실전 검증 대기"로 적는다. 1w·1m 범위는 과거 검증을 통과하지 않았으므로 사실과 다르다(CLAUDE.md: 검정을 통과하지 못하면 '우위 없음'으로 표시).
- 원인: `report.live_edge_at`(`backend/app/forecast/report.py:488-492`)이 `FORWARD_TEST_KINDS`(rank·range·vol)에 대해 `comp.edge`를 보기 전에 `forward_test_pending`을 돌려준다. 전략 쪽에서는 "전진 검증 전까지 보류"라는 뜻이었는데, 프론트엔드 `edgeLabel`·`BADGE_NOTE`·`REASON_LABEL`(`frontend/src/lib/forecast.ts:47-51`, `frontend/src/components/ForecastPanel.tsx:83-87,180-185`)이 이를 "과거 검증 통과 + 실전 대기"로 해석했다. `services/forecasts.py`는 그 값을 그대로 전달한다.
- 근거: verifier가 실제 서버에서 대조(2026-10-22 18:40 KST). `GET /api/forecasts/status` report의 `horizons.1w.comparisons["stock:range"].edge == false`(1m도 false, 1d만 true)인데 `GET /api/forecasts/<보유 주식>` 응답은 세 기간 모두 `range_reason == "forward_test_pending"`. `frontend/src/lib/forecast.test.ts` "collapses the two edge flags"와 `backend/tests/test_forecasts_api.py::test_symbol_forecast_has_ordered_ranges_and_verdicts`가 이 동작을 그대로 기대한다.
- 해결: 리드가 (b)로 결정(2026-10-23, evaluation-engineer 수정, D-028). `report.live_edge_at`이 `comp.edge`를 먼저 읽는다: comparison이 없으면 `no_data`, `edge`가 False면 kind와 무관하게 `not_significant`, True인데 kind가 `FORWARD_TEST_KINDS`(rank·range·vol)이고 `FORWARD_CONFIRMED`에 없으면 `forward_test_pending`(edge False 유지), 그 외 `edge`. `EdgeStatus.edge` 값은 어느 경우에도 바뀌지 않고 reason 문자열만 바뀌므로 S1·S2·`signals.py`와 실서비스 플래그의 동작은 같다. `PointInTimeEdge.status`(백테스트 시점 판정)는 건드리지 않았다: 전진 검증 보류가 없고(과거 시점에서는 의미가 없음) `insufficient_history`·`inconsistent_years`를 따로 내는 등 reason 체계가 원래 다르며, 바꾸면 기록된 백테스트 사유가 재현되지 않는다. 프론트 `BADGE_NOTE.pending`·`REASON_LABEL` 문구는 app-engineer 몫(ISSUE-038과 함께).
- 검증: `tests/test_forecast.py::test_live_edge_reason_reads_the_walk_forward_verdict_first`(edge False·forward kind → `not_significant`, edge True·forward kind·미확정 → `forward_test_pending`, edge True·direction → `edge`, comparison 없음 → `no_data`, `FORWARD_CONFIRMED`에 넣으면 `edge`, 실패한 비교는 넣어도 `not_significant`). 기대값 수정 2건: `test_live_range_and_vol_edges_wait_for_the_forward_test`의 rank를 `forward_test_pending` → `not_significant`(합성 변동성 데이터에서 rank는 walk-forward 미통과), `tests/test_forecasts_api.py::test_symbol_forecast_has_ordered_ranges_and_verdicts`의 `range_reason`을 report의 `stock:range` edge 플래그에서 계산(동작 변경 없음). 현재 run(20261021T163606) report 기준 자산군 2 × 기간 3 × kind 4 = 24칸 중 16칸이 바뀜: walk-forward를 통과하지 못한 range·rank 전부가 `forward_test_pending` → `not_significant`. `forward_test_pending`으로 남는 것은 `stock:range 1d` 하나, direction 6칸은 `not_significant` 그대로, vol 6칸은 이 run report에 없어 `no_data` 그대로. edge 플래그는 24칸 모두 False로 변화 없음. 백엔드 전체 pytest·`ruff check`·`ruff format --check` 통과. 실제 서버(8001)는 재시작 전이라 화면 대조(1w·1m 배지가 '기준선과 차이 없음', 1d 범위만 '실전 검증 대기')는 verifier가 재시작 뒤 한다. verifier 미확인.

### [ISSUE-038] 홈 모델 상태 문장이 범위 예측의 기준선 우위를 "시장 평균보다 나았다"로 표현함
- 현상: 홈 「앞으로의 예상 자산」 아래 `modelStatusSentence`가 현재 run에서 "일부 기간에서 시장 평균보다 나았습니다. 실전 검증이 끝날 때까지는 참고만 하세요."를 낸다. 근거는 `1d stock:range` edge 하나다. 이 비교는 GBDT 범위 예측 vs EWMA-t 변동성 기준선의 interval score 비교이고, 방향(오를 확률)은 모든 기간에서 기준선과 차이가 없다. "시장 평균보다 나았다"는 수익률이 시장을 이겼다는 뜻으로 읽힌다.
- 원인: 용어표가 "기준선"을 "시장 평균"으로 바꿨고(`frontend/src/lib/forecast.ts:62-64`), 범위·방향을 구분하지 않고 한 문장으로 합쳤다. `ForecastPanel.tsx:86`의 `BADGE_NOTE.none`("시장 평균보다 낫다는 증거가 없어요")도 같은 표현이다(이쪽은 보수적이라 과장은 아님).
- 근거: `GET /api/forecasts/status` report의 comparisons 플래그(verifier 2026-10-22, 18개 중 1d stock:range만 edge True), `frontend/src/lib/forecast.test.ts` "summarizes the report".
- 해결(2026-10-23, app-engineer 수정 라운드 1): `frontend/src/lib/forecast.ts`의 `modelStatusSentence`가 "시장 평균" 대신 "단순 기준선(과거에 오른 날 비율)"이라 부르고 방향·범위 판정을 따로 적는다. 원래 제안: 무엇이 무엇보다 나았는지 적는다. 예: "1일 뒤 가격 범위는 단순 변동성 기준선보다 정확했지만, 오를지 내릴지는 기준선과 차이가 없습니다(우위 없음). 실전 검증 전까지 참고만 하세요." edge가 없을 때의 문장과 `BADGE_NOTE`의 "시장 평균"도 "기준선"으로 맞춘다.
- 검증: verifier 발견(2026-10-22). 수정 후 문장은 `live` 판정에서만 나오며(`direction_reason`/`range_reason`), 프론트 verifier가 `grep "시장 평균" src` 0건을 확인한다(2026-10-23 프론트엔드 검증 섹션).

### [ISSUE-039] 1d 예측의 `target_date`가 이미 지난 날짜인데 "다음 거래일"로 표시됨
- 현상: 2026-10-22(목) 18:40 KST에 `GET /api/forecasts/<보유 주식>`의 1d 기간은 `as_of 2026-10-20`, `target_date 2026-10-21`이다. 종목 상세 「앞으로 예상」 첫 줄이 "다음 거래일 · 2026-10-21 기준"으로, 이미 지난 날짜의 예측을 미래처럼 보여 준다. 가격 차트는 `buildRows`가 마지막 봉 이후 날짜만 그리므로 이 기간을 건너뛴다(정상). 같은 지연 때문에 홈의 "오늘" 변동(`price_as_of` 10-20)도 실제로는 10-19→10-20 세션의 변동이다.
- 원인(확인된 부분): 같은 시각 `GET /api/market/SPY/quote`(as_of 10-20)와 `GET /api/market/SPY/history`, 보유 종목 history가 모두 10-20 봉에서 끝난다. 공급자 응답에 10-21 봉이 아직 없다. 추론은 `load_inputs` → `_load` → `get_history(final_only=True)`로 마지막 확정 봉을 as_of로 쓰므로, 10-21 봉이 오기 전까지 1d 목표일은 달력상 지난 날짜가 된다. 30분 추론 캐시(`INFERENCE_TTL`, 캐시 키는 run·보유 종목만)는 봉이 도착한 뒤 최대 30분 더 지연시키는 요인이지 지금의 원인은 아니다.
- 원인(가설): 공급자(yfinance)가 미국 장 마감(05:00 KST) 뒤 13시간이 지나도 전일 봉을 주지 않은 이유(공급자 지연인지 이 환경의 시계 문제인지)는 확인하지 않았다. 어느 쪽이든 "목표일이 지난 1d 예측"은 봉 도착 전 구간에 늘 생긴다.
- 근거: verifier 조회(2026-10-22 18:40 KST): `/api/forecasts/<보유 주식>` 1d `target_date < today`, `/api/market/SPY/quote` as_of `2026-10-20T00:00:00`, `/api/market/SPY/history?start=2026-10-15` 마지막 봉 10-20. `backend/app/forecast/data.py` `_load`(final_only=True), `backend/app/services/forecasts.py` `INFERENCE_TTL`·`_latest`.
- 해결(2026-10-23, app-engineer 수정 라운드 1, 화면만): `isPastTarget`/`pendingPhrase`로 목표일이 지난 기간을 "채점 대기 (MM.DD 마감 기준)"으로 표시하고, 홈·종목 상세 변동 라벨은 `quoteTime.ts`의 `changeLabel`이 "오늘"/"전일 대비"/"MM.DD 종가 기준"을 고른다. 원래 제안: `target_date < 오늘`인 기간은 "다음 거래일" 대신 "채점 대기(10-21 마감 기준)"처럼 표시하거나 요약 줄에서 빼고, 홈·종목 상세의 "오늘" 변동은 `price_as_of`가 오늘이 아니면 날짜를 함께 적는다. 백엔드 변경은 필요 없다.
- 검증: verifier 발견(2026-10-22). 프론트 테스트(`forecast.test.ts`, `quoteTime.test.ts`)와 리드 브라우저 확인(2026-10-23, 홈 라벨 "MM.DD 종가 기준").

### [ISSUE-040] 추론 캐시 키가 세션 마감을 모르고, 보유 주식의 10-21 봉 기준 예측은 하루 내내 한 번도 만들어지지 않음
- 현상: ISSUE-039의 백엔드 후속. 실제 DB `forecast_log`(읽기 전용 조회, 2026-10-23 10:30 KST)에서 1d 행의 `as_of`는 10-20(10-21 19:36 KST 생성, 그리고 보유 종목이 추가된 10-22 16:59 KST에 다시 생성) 다음이 바로 10-22(10-23 10:28 KST 생성)다. `as_of` 10-21 행은 어느 종목에도 없다. 즉 10-22 05:30 KST(10-21 세션 마감 + 정산 30분)부터 10-23 05:30 KST까지, 추론이 다시 돈 10-22 16:59에도 보유 주식의 마지막 확정 봉은 10-20이었다. 2026-10-23 10:28 KST 조회에서는 1d가 `as_of 10-22, target_date 10-23`으로 정상이다.
- 원인(확인): 리드가 지목한 두 경로를 코드로 확인했다. ① `load_inputs`(`backend/app/forecast/data.py`)는 보유 종목과 맥락 시리즈를 `max_age=None`으로 읽는다(`stale_ok`는 참조 종목에만 적용). `get_history(final_only=True)`는 마지막 동기화가 15분(`HISTORY_TTL`)을 넘었거나 진행 중이던 봉이 그 사이 마감됐으면(`_closed_since_sync`) 다시 받으므로, 이 경로의 지연 상한은 15분이다. 동기화를 건너뛰지 않는다. ② `ForecastService._latest`의 추론 캐시 키는 `(run_id, 보유 종목)`뿐이라 세션이 마감되어도 바뀌지 않는다. 봉이 캐시에 들어온 뒤에도 최대 30분(`INFERENCE_TTL`) 전 세션 기준 결과(지난 1d 목표일)를 돌려준다. ①+②의 상한은 45분이라 13시간을 설명하지 못한다.
- 원인(가설): 나머지는 공급자 쪽이다. (a) Yahoo가 10-21 봉을 빼고(또는 종가 NaN으로, `validate_bars`가 버림) 응답했다. verifier가 같은 시각 `period="5d"` 경로인 `/api/market/SPY/quote`에서 as_of 10-20을 받은 것과 맞고, ISSUE-010이 코인에서 본 "자정 뒤 몇 시간 동안 전날 봉이 빠진다"와 같은 형태다. (b) yfinance는 오류를 예외로 올리지 않고 빈 DataFrame을 돌려주는 경우가 있다. 그러면 `_sync`가 "refresh returned no bars; cache left as it was" 경고만 남기고 `synced_at`을 옮기지 않아, 요청이 계속 실패하는 동안 옛 캐시가 조용히 유지된다(예외였다면 `_load`가 종목을 빼서 `insufficient_history`가 났을 것이다). (b)는 quote가 데이터를 돌려준 사실과 맞지 않아 (a)를 유력하게 본다. 당시 공급자 응답 원본과 서버 콘솔 경고는 남아 있지 않아 확정하지 못했다.
- 근거: 실제 DB `forecast_log`·`symbol_syncs` 읽기 전용 조회(종목명·수량 제외), `backend/app/forecast/data.py` `_load`·`load_inputs`, `backend/app/services/market_data.py` `get_history`·`_sync`·`_closed_since_sync`, `backend/app/data/yfinance_provider.py` `_download`, `backend/app/services/forecasts.py` `_latest`, ISSUE-010·039.
- 해결: ②만 고쳤다(app-engineer, 2026-10-23). `ForecastService._bar_epoch`가 달력 기준으로 "지금 확정돼 있어야 하는 마지막 주식·코인 봉 날짜"(`calendar.last_final_date`, SPY·BTC-USD 달력, 정산 지연 포함)를 구해 캐시 키에 넣는다. 세션이 마감되면 다음 요청이 바로 다시 계산한다(자산군당 하루 1회 추가 재계산). 공급자가 아직 봉을 안 줬으면 결과는 같고 30분 뒤 다시 시도한다(기존과 같음). ①은 바꿀 것이 없다. 공급자 지연 자체(a·b 구분, 빈 응답 시 경고를 상태로 노출할지)는 data-engineer 영역이고, 지난 목표일의 화면 표시는 ISSUE-039대로 프론트가 처리한다.
- 검증: `backend/tests/test_forecasts_api.py::test_inference_is_rebuilt_once_a_new_session_has_closed`(마지막 확정 봉 날짜가 바뀌면 `_compute`가 다시 호출되고, 바뀌지 않으면 캐시를 쓴다). 실제 서버는 재시작하지 않았으므로 코드 반영 전이다. verifier 미확인.

### [ISSUE-041] Norges Bank 13F의 Q1·Q3 표가 기밀 처리로 비어 있어 최신 분기 기준 스냅샷이 반년 동안 오류·stale이 됨
- 현상: EDGAR 회사 검색(Chrome, 2026-10-23)에서 NORGES BANK(CIK 0001374170)의 13F-HR 제출 크기가 분기마다 4KB와 830~900KB로 번갈아 나온다. 2026-05-11 제출(Q1 2026) `0001374170-26-000023`의 `primary_doc.xml`은 `isConfidentialOmitted=true`, `tableEntryTotal=1507`, additionalInformation에 "pursuant to a request for confidential treatment"이고, 정보 테이블 `Q1_2026_0.xml`은 627바이트(행 없음)다. 같은 날 제출된 13F-HR/A `0001374170-26-000021`은 1년 전 분기(Q1 2025)의 표를 `amendmentType=NEW HOLDINGS`, `reasonForNonConfidentiality=Confidential Treatment Expired`로 공개한다(852KB, 1,743종목). Q2·Q4 원본(2026-08-12, 2026-02-10, 2025-08-13, 2025-02-12)은 전체 표다. 수정 전 `choose_filings`는 보고 분기가 가장 최근인 13F-HR 하나만 고르므로 11~2월·5~8월에는 빈 표를 받아 `_rows_to_snapshot`이 "no equity rows"로 실패하고, 서비스는 마지막 성공 스냅샷을 유지하되 `error`·`stale`로 표시한다. 같은 날의 /A는 accession이 원본보다 작아 amendment 조건에서 빠진다(1년 전 분기라 합치면 안 되므로 결과적으로 맞다).
- 원인: 제출자의 기밀 처리 요청(확인). 왜 Q1·Q3만인지는 가설: 노르웨이 국내 공시가 반기(연말·반기말)라 그에 맞춰 Q2·Q4만 바로 공개하는 것으로 보인다. 2025~2026 네 분기 연속 같은 패턴을 관찰했다.
- 근거: EDGAR 회사 검색 결과와 위 두 제출 문서의 `primary_doc.xml`(브라우저로 직접 열어 읽음). `backend/app/data/guru_provider.py`의 수정 전 `choose_filings`·`_rows_to_snapshot`.
- 해결(data-engineer, 2026-10-23, D-030): `choose_filing_sets`가 보고 분기별 [원본, 이후 amendment…] 묶음을 최신순으로 돌려주고, `Sec13FProvider.fetch`는 최신 묶음의 표가 비어 있으면(`EmptyTableError`) 최대 `MAX_QUARTERS_BACK`=2분기 전까지 물러나 행이 있는 분기를 쓴다. 스냅샷 `note`에 "기밀 처리로 표가 비어 있는 분기 제외: {분기}. {분기} 기준 표를 표시"를 적어 화면이 `sync_note`로 보여 줄 수 있다. 세 분기가 모두 비어 있으면 빈 포트폴리오 대신 오류로 남긴다. `choose_filings`는 첫 묶음을 돌려주는 래퍼로 유지했다.
- 검증: `tests/test_gurus.py::test_sec_provider_falls_back_to_previous_quarter_when_table_is_confidential`(Q2 빈 표·Q1 전체 표 → `as_of` Q1 말, note에 두 분기 날짜; 전부 빈 표 → `EmptyTableError`), `test_choose_filing_sets_orders_quarters_newest_first`. 실제 EDGAR 호출은 `AM_SEC_USER_AGENT`가 비어 있어 하지 않았다(사용자 설정 대기). verifier 미확인.

### [ISSUE-042] pypdf가 하원 PTR 양식의 small-caps 라벨 소문자를 NUL 문자로 뽑아 행 구분이 깨짐
- 현상: 하원 서기국 PTR PDF(전자 제출본, 2026-09-09 제출 샘플 1건, 8쪽 78행)에 `extract_text`를 돌리면 양식의 small-caps 라벨이 `"F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New"`("Filing Status: New"), `"P\x00… T\x00… R\x00…"`("Periodic Transaction Report")처럼 소문자 자리가 NUL(U+0000)로 나온다. NUL을 모르는 첫 파서는 "F S: New" 행 구분 라벨을 인식하지 못해 구형 레이아웃 경로(거래 필드 기준 분할)로 떨어졌고, 직전 행의 라벨 텍스트가 다음 행 앞에 붙어 Owner 코드 78행이 전부 `SELF`로 나오고 자산명에 라벨 찌꺼기가 섞였다(실제 문서는 78행 모두 `DC`).
- 원인(확인): 양식의 라벨 글꼴이 small caps라 소문자 글리프에 유니코드 매핑이 없고, pypdf 6.21.x가 매핑 없는 글리프를 NUL로 내보낸다. 시스템 Python(pypdf 6.21.1)과 venv(6.21.2)에서 같다.
- 근거: 스크래치 `finnhub_probe/dump_text.py`로 뽑은 줄별 repr(라벨 줄에 `\x00` 반복), 수정 전 `validate_parser.py` 결과(owners `SELF` 78, 경고 "unparsed trailing text: F S : New"), 수정 후 결과(owners `DC` 78, 경고 0, 티커 33종, 금액 구간 5종, 페이지를 넘는 행 정상). 스크립트와 샘플 PDF는 세션 스크래치 폴더에만 있고 저장소에는 가상 데이터 fixture만 넣었다.
- 해결(data-engineer, 2026-10-23): `parse_ptr_text`가 맨 먼저 `text.replace("\x00", "")`로 NUL을 제거하고, 머리글 정규식 `_HEADING`을 글자 사이 공백 1칸 이상(`^(?:[A-Z]\s+)*[A-Z]\s*$`)으로 넓혀 "P T R"·"F I"·"T"를 걷어낸다. 라벨 정규식 `_LABEL`은 "F S: New"·"D : …"를 키 "FS"·"D"로 읽는다. 라벨이 하나도 없는 문서만 구형 경로를 탄다.
- 검증: `tests/test_congress.py::test_parse_ptr_text_drops_nul_characters_of_small_caps_labels`(NUL 포함 문자열 → owner `DC`, filing_status `New`, 금액 구간), `test_parse_ptr_text_reads_rows_across_wraps_and_pages`(가상 5행: 여러 줄 자산명, 페이지 넘김, `S (partial)`, `Over $50,000,000`, Owner 코드, Amended, 자본이득 Yes, 설명 라벨). 실제 샘플 1건 78행 전부 파싱(경고 0). 종이 제출 스캔본(텍스트 없음; 2026년 PTR 435건 중 7자리 DocID 53건이 그것이라는 것은 가설)은 `no_text`로 기록하고 화면에 건수만 적는다. verifier 미확인.

### [ISSUE-043] 백엔드가 `schema.d.ts`를 재생성한 뒤 하원 거래 테스트 픽스처가 `syncing`을 빠뜨려 `npm run build`가 실패함
- 현상: 2026-10-23 16:01 `frontend/`에서 `npm run build`(`tsc -b && vite build`)가 TS 오류 2건으로 멈춘다. `src/components/CongressTrades.test.tsx(32,3)` TS2322, `src/pages/Compare.test.tsx(53,7)` TS2741 — 둘 다 "`syncing`이 `CongressStatusOut`에 필수인데 픽스처에 없음". `npm test`(vitest, 타입 검사 없음) 26 파일 150개와 `npm run lint`(oxlint)는 통과한다.
- 원인(확인): 백엔드가 `CongressStatusOut`에 `syncing: bool`을 추가하고 15:57에 `openapi.json`·`schema.d.ts`를 재생성했다(`app/export_openapi`를 스크래치로 다시 뽑아 `openapi.json`과 비교하면 동일). 프론트 테스트 픽스처(15:43~15:45 작성)는 그 전 스키마를 따랐고, `tsconfig.app.json`이 `include: ["src"]`라 테스트 파일도 `tsc -b`에 들어간다.
- 근거: 위 tsc 출력, `stat` mtime(`schema.d.ts` 15:57:29, `CongressTrades.test.tsx` 15:45:14), `git diff -- frontend/src/api/schema.d.ts`.
- 해결: (app-engineer) 두 픽스처에 `syncing: false`를 넣는다. verifier가 16:0x에 app-f2에 전달.
- 검증: app-f2가 16:03 두 픽스처에 `syncing: false` 추가. verifier 재실행(트리 `3c5f93d2…`) `npm run build` 통과, oxlint 경고 0, vitest 26 파일 150개 통과. 해결.

### [ISSUE-044] 하원 거래 카드의 "(하루 60건씩)" 문구가 백엔드 배치 동작과 다르고 설정값을 프론트에 하드코딩함
- 현상: `frontend/src/components/CongressTrades.tsx:100`이 `docs_pending > 0`일 때 "`{n}건 더 받는 중(하루 60건씩)`"을 보여 준다.
- 원인(확인): 백엔드 `app/services/congress.py:60-63`은 한 번 트리거에 `MAX_DOCS_PER_SYNC = 60`건 배치를 `MAX_BATCHES_PER_SYNC = 10`회까지 연속 실행한다(모듈 docstring: "a first visit's year of backlog … is fetched in one background run instead of one batch a day"). 배치 수는 `AM_CONGRESS_MAX_BATCHES`로 바뀐다. 하루 60건이 아니고, 바뀔 수 있는 설정값이 화면 문구에 박혀 있다.
- 근거: 위 코드 위치, `app/api/congress.py:35` `run_sync(..., max_batches)`.
- 해결: (app-engineer) 숫자를 빼고 "n건 더 받는 중"만 두거나, 백엔드가 응답에 넣는 값으로 바꾼다. 비차단.
- 검증: app-f2가 16:03 `CongressTrades.tsx:101`을 "`{n}건 더 받는 중`"으로 바꿈(숫자 제거). 테스트 `:171` 기대 문구도 함께. verifier가 소스·dev 서버 서빙 모듈(`하루` 0건)에서 확인. 해결.

### [ISSUE-045] 하원 PTR 파서가 페이지 경계로 갈라진 금액 상한 행을 버리고, `D:` 둘째 줄을 가짜 unparsed로 세고, 점 표기 티커를 정규화하지 않음
- 현상: verifier가 실제 공개 PDF 51문서(592행)를 재파싱해 비교한 결과 2행(0.3%)이 DB에 없었고(금액 "$X -"와 "$Y" 사이에 페이지 머리글과 자산명 나머지 줄이 끼는 경우), `congress_docs.error` 4건 중 2건은 `D:` 설명이 두 줄인 문서의 둘째 줄이 `unparsed`로 기록된 것이었으며, `BRK.B`·`MOG.A`처럼 점 표기 티커 5행이 앱 표기(`BRK-B`)와 매칭되지 않았다. 또 `POST /api/congress/sync`가 TTL 24시간 안이면 `syncing: true`만 돌려주고 아무것도 하지 않아 첫 동기화 뒤 남은 백로그 469건이 다음 날까지 그대로였다(VERIFICATION.md F-2 백엔드 섹션 N-F2B-1·2·4·8).
- 원인: `_AMOUNT_TAIL`이 바로 다음 줄만 봤다. 라벨(`D:` 등) 값의 연속 줄을 합치지 않았다. 심볼 정규화 함수가 없었다. 동기화 due 판정이 pending 문서 수를 보지 않았다.
- 근거: `backend/app/data/congress_provider.py`(`_AMOUNT_TAIL`, `parse_ptr_text`의 `open_label`), `backend/app/services/congress.py`(`_is_due`, `trades`, `_run`), verifier 재현 스크립트(스크래치 `verify-be/`).
- 해결(2026-10-23, data-engineer): 금액 꼬리를 다음 3줄 안에서 찾음(`_AMOUNT_TAIL_LINES=3`, 행 시작처럼 보이는 줄은 제외). 라벨 연속 줄을 값에 이어 붙임. `normalize_symbol`(`.`·`/`→`-`, 대문자)을 저장·조회 양쪽에 적용하고 매 배치 기존 행을 SQL UPDATE로 바로잡음. 한 번도 받지 않은 문서가 남아 있으면 TTL과 무관하게 10분 뒤 다시 due(`BACKLOG_RETRY`)이고, 실패 문서만 남으면 24시간 TTL을 따른다(서기국이 못 주는 PDF 하나 때문에 10분마다 색인 ZIP을 다시 받지 않도록). `/sync`·`/trades`는 `due()`일 때만 배경 작업을 걸고 `syncing`은 실제로 작업이 걸렸을 때만 true. `_CAP_GAINS`의 ``도 `(?![A-Za-z])`로 고쳐 줄 끝 ✓·Yes를 인식.
- 검증: `tests/test_congress.py`(20)·`tests/test_congress_service.py`(19)·`tests/test_congress_api.py`(4), 전체 pytest 610 passed. 실제 서버 백로그 소진은 verifier가 `fetched_at`으로 복원해 확인(VERIFICATION 부록: 8배치 약 40초).
- 회귀(2026-10-23 저녁, verifier 재확인에서 발견): 위 "라벨 연속 줄을 값에 이어 붙임"이 실제 PTR 레이아웃(행 → `F S:` → `S O:` → `D:` → 다음 행)에서 다음 행의 자산명 첫 줄을 `S O`/`D` 값에 붙여 버렸다. 공개 PDF 14건에서 624행/133 warning(연속 규칙을 끄면 751행/8)으로 행 17%가 빠지고 자산명 394행이 `(GOOG)`처럼 잘렸다. 실제 DB에도 77문서 351행 unparsed·잘린 자산명이 저장돼 있었고, `parsed` 문서는 다시 읽는 경로가 없어 파서만 고치면 DB가 그대로 남는 문제가 함께 드러났다. 픽스처는 `D:`가 `F S:` 앞에 있고 `S O:`가 없어 테스트가 잡지 못했다.
- 회귀 해결(2026-10-23, data-engineer): `parse_ptr_text`의 라벨 처리를 다시 짰다. 모든 행 뒤에 오는 `F S`(filing status)를 행 경계로 쓰고, 값이 줄바꿈될 수 있는 라벨은 `D`·`C`(`_FREE_TEXT_LABELS`)만으로 한정해 `S O`·`F S` 뒤의 줄은 다음 행으로 넘긴다. 픽스처 `ptr_text_sample.txt`를 실제 순서로 바꾸고 SELF 소유 두 줄 행이 라벨 뒤에 오는 케이스를 `test_labels_under_a_row_never_swallow_the_next_row`로 고정했다. 저장된 문서는 `services/congress.py`의 `REPARSE_BEFORE`(UTC 시각 상수) 이전에 파싱된 `parsed` 문서를 다음 동기화 때 새 문서·실패 문서 뒤 순서로 한 번 다시 받아 그 문서의 행을 한 트랜잭션에서 지우고 다시 넣는다(`_to_reparse`, `_is_due`는 재파싱 잔량이 있으면 10분 뒤 다시 due). 파서를 또 고치면 이 상수를 수정 시각 이후로 옮긴다(D-030 8항).
- 회귀 검증(2026-10-26, verifier 부록 2): 같은 14건이 757행/0 warning(연속 규칙 끔 751보다 6행 많은 것은 `$2,000.00`·`Spouse/DC Over …` 표기도 읽기 때문), 자산명 `(` 시작 0행, `D:` 53행이 모두 제 행에 붙음. 테스트 22·20·4, 전체 pytest 613 passed, gen:api 산출물 불변. 실제 DB의 parsed 460건 중 365일 창 안 458건이 다음 동기화 때 다시 읽힌다(60×10배치 한 트리거 안). 남은 한계: `status`의 `docs_pending`이 재파싱 잔량을 포함하지 않음(N-F2C-1), 문서 중간 두 줄 `D:` 조각이 다음 행 자산명 앞에 붙을 수 있음(14건에서 0건, TODO_FOR_ME). N-F2C-1은 `status().docs_pending`에 재파싱 잔량을 더해 해결(2026-10-26).

### [ISSUE-046] 캔들 보기 읽기판(`BarReadout` 오버레이)이 lightweight-charts 캔버스 아래에 깔려 보이지 않음
- 현상: 리드가 브라우저에서 종목 상세를 캔들 보기로 바꾸자 왼쪽 위 읽기판이 DOM에는 있으나 화면에 보이지 않았다(2026-10-26). vitest(jsdom)는 캔버스를 그리지 않아 통과했다.
- 원인: lightweight-charts 5.2.1이 캔버스를 `position:absolute`에 `zIndex '1'`·`'2'`로 쌓고 배경을 불투명하게 칠한다. 오버레이 `div`는 `absolute`였지만 z-index가 없어, DOM 순서상 뒤에 있어도 z-index 1·2 아래로 그려졌다.
- 근거: `frontend/node_modules/lightweight-charts/dist/lightweight-charts.development.mjs`에 `zIndex = '1'` 3곳·`zIndex = '2'` 3곳(verifier grep). 수정 전 `CandleChart.tsx` 오버레이 클래스 `pointer-events-none absolute top-2 left-2 … bg-surface/85`.
- 해결(2026-10-26, app-engineer): 오버레이 클래스에 `z-10` 추가 + 이유 주석. `CandleChart.test.tsx`(신규, `vi.mock('lightweight-charts')`로 마운트)가 `z-10`·`pointer-events-none`, 크로스헤어 콜백으로 봉 전환(문자열·BusinessDay time), 빈 `seriesData`면 마지막 봉 복귀를 고정.
- 검증: verifier가 dist CSS에 `.z-10{z-index:10}` 생성, 번들의 zIndex 1·2, vitest 28 files/167 tests(build·oxlint 0) 확인. 리드가 브라우저에서 재확인(2026-10-26): 라이트·다크 모두 읽기판이 캔버스 위에 보이고 호버한 봉으로 바뀌며 벗어나면 마지막 봉으로 돌아옴.

### [ISSUE-047] 직접 입력으로 가져온 거래의 메모가 "스크린샷 가져오기"로 기록되고, 일괄 삭제 문구도 "스크린샷으로 가져온 거래"라 출처가 틀리게 보임
- 현상: `POST /api/imports/manual`로 만든 행을 `POST /api/imports/commit`으로 기록하면 `transactions.note == "스크린샷 가져오기"`가 된다(verifier 프로브, 메모리 DB, 합성 AAPL 3주: `tx note: 스크린샷 가져오기`). 거래 페이지 메모(`frontend/src/pages/Transactions.tsx:177`)와 일괄 삭제(`frontend/src/components/BulkDelete.tsx:8,25` "스크린샷으로 가져온 거래 N건을 삭제할까요?")가 이 메모를 그대로 쓴다.
- 원인: `CommitRow`/`CommitRowIn`에 출처가 없고 `services/statement_import.py` `commit()`이 모든 행에 `note=IMPORT_NOTE`(`services/transactions.py:18`) 상수를 붙인다. `PreviewRow.origin`은 미리보기 응답에만 있다.
- 근거: 위 코드 위치. app-engineer 보고에 "담당 외 파일이라 두었음"으로 인지되어 있음.
- 해결: 미정(낮음, 비차단). 선택지 ① `IMPORT_NOTE`를 출처 중립 문구로 바꾸고 `BulkDelete` 문구도 "가져온 거래"로(기존 DB의 옛 메모와 호환되게 `only_imported`·프론트 필터가 두 문구를 모두 허용) ② `CommitRowIn.origin`을 받아 메모를 "직접 입력"으로 나눔. 담당: 리드 배정(`services/transactions.py`·`BulkDelete.tsx`).
- 검증: 미해결. 재현은 VERIFICATION.md "가져오기 직접 입력 (2026-10-26)"의 `probe.py`.

### [ISSUE-048] 단가가 수천 배 틀린 가져오기 거래가 있으면 코치의 "실제 추이 낙폭"과 월간 리뷰 입금 분해가 불가능한 값을 사실처럼 보여 줌 (verifier N-COACH-1)
- 현상: 데모 DB에 원화 총액을 USD 단가로 기록한 직접 입력 검증 행 5건(원가/평가 3,946~68,783배, 앱의 20배 `단가 확인` 규칙에 걸리는 행)이 남아 있었다. `GET /api/coach/diagnosis`의 `risk.actual`이 `twr_max_drawdown_pct` 598,141%, `current_drawdown_pct` 584,636%를 내고 `actual_error`는 null이었다. 월간 리뷰 2026-10은 넣은 돈 3,398억원·시장 손익 −3,398억원(자산 5,818만원)으로 분해됐다. 화면은 "−598141.2%"·"지금 고점 대비 −584636.7%"를 그대로 적었다.
- 원인: `benchmarks.cash_flows`가 거래 금액(수량 × 틀린 단가)을 그날 입금으로 잡아 평가액을 수만 배 넘는 입금이 생기고, `strategy/coach.twr_index`가 `V_d − f_d ≤ 0`(= `1 + r_d ≤ 0`)인 날을 거부하지 않아 지수가 음수로 넘어갔다. 단서 문구는 "가져온 거래의 날짜"만 말하고 단가는 말하지 않았다.
- 근거: `docs/dev/VERIFICATION.md` "포트폴리오 코치 (2026-10-27)" N-COACH-1(재현 스크립트 경로 포함). 메모리상 실제 사용자 DB에도 단가가 틀린 가져오기 행이 있어 실서비스에서도 재현 가능성이 높다.
- 해결(2026-10-27): ① risk-engineer — `twr_index`를 fail-closed로: 평가액이 음수이거나 `V_d − f_d ≤ 0`인 날이 있으면 날짜·원인을 담은 한국어 `ValueError`("…입금을 뺀 수익률이 -100% 이하라 시간가중 지수를 만들 수 없습니다(단가가 틀린 거래가 있는지 거래 페이지에서 확인하세요)"). `V_{d-1} == 0`인 날은 기존대로 수익률 0으로 둔다(전량 매도 뒤 재매수가 정상 사용이고 `portfolio.history()`가 그런 날을 0으로 내기 때문). ② app-engineer — 서비스가 이 ValueError를 잡아 `actual=None`·`actual_error`로 응답하고, 거래 통화 단가가 거래일 종가와 20배 이상 차이 나는 "단가 확인" 거래가 있으면 실제 추이 낙폭을 계산하지 않고 그 사실(건수·종목)을 `actual_error`에 적으며, 월간 리뷰는 장부 사실인 입금·시장 손익은 그대로 두되 `suspicious_trades`와 단서를 붙이고 화면은 그 숫자에 손익 색을 쓰지 않는다. 근본 해결은 사용자가 거래 페이지에서 단가를 고치는 것이다(TODO_FOR_ME).
- 대안(미채택, risk-engineer 제안): 시작 시점 유입 가정 `r = (V_d − V_{d−1} − f_d)/(V_{d−1} + f_d)`는 이 병리를 수식 차원에서 없애지만 `tests/test_coach_math.py`가 현재 공식을 손계산으로 고정하고 있어 별도 결정으로 미룬다.
- 검증: `tests/test_coach.py`에 fail-closed 테스트(정확히 −100%도 거부, 첫 위반일 보고, 음수 거부, 0 구간 재시작) 추가, `test_coach_api.py`에 단가 20배 틀린 매수로 `actual=None`·`actual_error` 확인. verifier 재검증은 수정 라운드 뒤 리드가 테스트·브라우저로 확인(아래 PROGRESS 참고). verifier 재검증(2026-10-27) **해결 확인**: 데모 DB에서 `risk.actual=null`·`actual_error` "단가 확인이 필요한 거래 5건(…)", 598,141% 소멸, 창 수치 독립 재계산 117항목 차이 0; 같은 자산 추이·입금으로 `twr_index`를 직접 부르면 ValueError(2026-10-19), 20배 필터를 끈 서비스 경로도 `actual_error`로 닫힘; 리뷰 2026-10 `suspicious_trades=5`·caveats[0] 단가 확인 문장. pytest 883·vitest 220·ruff·oxlint·build 통과. 상세 `VERIFICATION.md` "수정 라운드 재검증". 남은 권고 N-COACH-10(20배 경계·분할 복원 직접 테스트 없음).
