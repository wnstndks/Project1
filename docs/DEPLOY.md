# 배포 안내 — 내 PC + Cloudflare Tunnel (1단계: 읽기 전용 데모)

이 문서는 앱을 인터넷에서 볼 수 있게 올리는 순서를 적는다. 결정 배경은 [`docs/dev/DECISIONS.md`](dev/DECISIONS.md)의 D-035, 파일별 설명과 문제 해결은 [`deploy/README.md`](../deploy/README.md)에 있다.

## 무엇이 공개되나

공개되는 것은 **가짜 장부로 도는 읽기 전용 데모** 하나뿐이다. 내가 실제로 쓰는 앱(8001번, 실제 장부)은 지금처럼 내 PC 안에서만 열린다.

```text
방문자 ── https ──> Cloudflare ── 터널 ──> [tunnel 컨테이너] ──> [demo 컨테이너]
                                                                  · 가짜 장부(seed) + 실제 시세
                                                                  · 저장·수정은 전부 403

내 PC 안에서만:  http://localhost:8001 (실제 장부)  ← 컨테이너는 이 DB·.env·모델 파일을 볼 수 없다
```

데모가 하는 일과 하지 않는 일:

| 항목 | 동작 |
| --- | --- |
| 장부 | `backend/seed/`의 데모 거래. 실제 보유 내역은 이미지에도 볼륨에도 없다 |
| 시세 | 실제 시세(yfinance·업비트). 받지 못해도 합성 시세로 바꾸지 않는다 |
| 저장·수정 | `/api`의 쓰기 요청은 모두 403(`demo_read_only`). 장기 시뮬레이션처럼 계산만 하는 요청만 허용 |
| 종목 조회 | 데모 장부·벤치마크에 있는 종목만. 다른 티커는 403(`demo_symbol_not_allowed`) |
| 요청 제한 | 방문자 주소당 분당 120회(기본값) |
| 예측 모델 | 이미지에 모델 파일이 없어 화면이 "모델 없음"으로 답한다(학습된 모델에는 실제 보유 종목이 들어 있어 싣지 않는다) |
| API 문서 | 꺼짐. `/openapi.json`은 404이고, `/docs` 주소는 문서 대신 앱 화면이 뜬다 |
| 실매매 | 꺼짐. 데모와 실매매를 함께 켜면 서버가 시작을 거부한다 |

## 준비

- Docker Desktop이 설치돼 있고 **켜져 있어야** 한다(트레이의 고래 아이콘이 멈춰 있으면 준비 완료).
- 임시 주소(quick 터널)는 Cloudflare 계정이 필요 없다. 고정 주소(named 터널)만 계정과 도메인이 필요하다.
- PC가 꺼지거나 절전에 들어가면 데모도 내려간다. Docker Desktop이 로그인할 때 자동으로 시작되게 해 두었다면(Settings → General) 컨테이너도 따라 올라온다. 직접 정지한 컨테이너는 올라오지 않고, quick 터널 주소는 시작할 때마다 새로 바뀐다.

## 1. 먼저 내 PC에서만 띄워 보기

PowerShell에서:

```powershell
cd deploy
Copy-Item .env.example .env          # 처음 한 번
```

`deploy/.env`를 열어 `COMPOSE_PROFILES=quick`을 `COMPOSE_PROFILES=`(빈 값)로 바꾼 뒤:

```powershell
docker compose up -d --build         # 첫 빌드는 몇 분 걸린다
docker compose ps                    # demo가 healthy가 될 때까지(첫 시작은 시세를 받느라 보통 1분 안, 네트워크에 따라 더)
```

오래 `starting`에 머물면 `docker compose logs demo`를 본다. 첫 시작은 데모 장부의 단가를 실제 시세에서 받는데, 받지 못하면 빈 데모를 띄우지 않고 약 5분 뒤 다시 시도한다(합성 시세로 바꾸지 않는다).

브라우저에서 `http://127.0.0.1:8010`을 연다. 확인할 것:

- 화면 위에 데모 안내 띠가 보인다.
- 거래 추가·규칙 저장 같은 쓰기가 "데모에서는 저장·수정할 수 없어요"로 막힌다.
- 홈·종목 상세·코치·공부 화면이 뜬다.

## 2. 임시 주소로 공개하기 (quick 터널)

`deploy/.env`의 값을 `COMPOSE_PROFILES=quick`으로 되돌리고:

```powershell
docker compose up -d
docker compose logs tunnel           # https://<단어들>.trycloudflare.com 줄을 찾는다
```

그 주소가 공개 주소다. **컨테이너를 다시 시작할 때마다 주소가 바뀌므로** 이력서·포트폴리오에 적을 주소로는 맞지 않는다. 잠깐 보여 줄 때 쓴다.

## 3. 고정 주소로 공개하기 (named 터널)

Cloudflare 계정과, Cloudflare에 연결된 도메인이 필요하다. 계정·도메인·토큰은 직접 만든다.

1. Cloudflare Zero Trust 대시보드 → Networks → Tunnels에서 터널을 만든다(커넥터 종류는 Docker).
2. 그 터널에 공개 호스트 이름을 추가한다. 예: `demo.내도메인`. 서비스는 `http://demo:8000`으로 적는다.
3. 터널 토큰을 복사해 `deploy/.env`에 적는다.

   ```text
   COMPOSE_PROFILES=named
   TUNNEL_TOKEN=<복사한 토큰>
   DEMO_HOSTNAME=demo.내도메인
   ```

4. 다시 띄운다.

   ```powershell
   docker compose --profile quick down      # quick 터널을 쓰고 있었다면 먼저 내린다
   docker compose up -d
   ```

   첫 줄은 데모 앱도 함께 내렸다가 둘째 줄에서 다시 띄운다(데모 DB는 남는다). 터널 종류를 바꿀 때는 이 순서가 필요하다. `up -d`만으로는 이전 터널 컨테이너가 내려가지 않는다.

토큰은 비밀값이다. `deploy/.env`에만 두고(이 파일은 커밋되지 않는다) 채팅·문서·스크린샷에 붙이지 않는다.

Cloudflare에서 페이지에 스크립트를 끼워 넣는 기능(Web Analytics 자동 삽입, Rocket Loader 등)은 켜지 않는다. 앱이 같은 출처의 스크립트만 허용하도록 보안 정책(CSP)을 보내므로, 켜면 그 스크립트가 막히고 화면이 깨질 수 있다.

## 평소 운영

```powershell
cd deploy
docker compose ps                                          # 상태
docker compose logs -f demo                                # 앱 로그
docker compose up -d --build                               # 코드를 고친 뒤 다시 빌드해 교체
docker compose --profile quick --profile named down        # 정지(데모 DB는 남는다)
docker compose --profile quick --profile named down -v     # 데모 DB까지 삭제(다음 시작 때 새 데모 장부)
```

공개 전에 한 번 돌려 볼 점검 명령(쓰기 403, 이미지 안에 비밀·DB·모델 파일 없음, 호스트 경로 마운트 없음)은 [`deploy/README.md`](../deploy/README.md)의 "확인" 절에 있다.

## 실제 장부 백업

데모와 무관하게, 내가 쓰는 실제 장부는 주기적으로 백업한다. 서버가 켜져 있어도 된다.

```powershell
.\scripts\backup-db.ps1                                # → %USERPROFILE%\asset-manager-backups, 최근 14개 유지
.\scripts\backup-db.ps1 -DestDir D:\backups -Keep 30
```

백업에는 실제 보유 내역이 들어 있다. 저장소 폴더 안이나 컨테이너가 볼 수 있는 폴더에 두지 않는다. 매일 새벽 3시에 자동으로 돌리려면 작업 스케줄러에 등록한다(경로는 내 저장소 위치로 바꾼다).

```powershell
schtasks /Create /TN asset-manager-backup /SC DAILY /ST 03:00 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\경로\project\scripts\backup-db.ps1"
```

## 공개 데모를 돌리는 PC에서 지킬 것

컨테이너는 실제 장부 **파일**을 볼 수 없다. 다만 Docker Desktop의 컨테이너는 이 PC의 localhost 서비스와 집 네트워크에 접속할 수 있다. 데모 앱 자체가 뚫리는 경우(데모는 읽기 전용이고 업로드가 없어 가능성은 낮지만 0은 아니다), 공격자가 같은 PC의 8001번 실제 앱에 요청을 보낼 수 있다는 뜻이다. 실제 앱에는 기본적으로 로그인이 없어, 그대로면 장부를 읽고 고치고 지울 수 있다.

그래서 공개 데모를 돌리는 PC에서는:

- **실제 앱(8001)에 항상 로그인을 켜 둔다**(아래 "로그인"). 데모를 켤 때만 켜는 방식은 잊기 쉬우니 상시로 둔다.
- 로그인은 장부만 지킨다. 쓰지 않는 다른 로컬 서비스(다른 프로젝트의 개발 서버, 로컬 LLM 서버 등)는 데모를 공개하는 동안 내려 둔다. 공유기 관리 화면과 NAS에는 기본 비밀번호를 쓰지 않는다.
- `deploy/.env`의 `DEMO_SEC_USER_AGENT`에 연락처 메일을 적으면 그 값이 데모 컨테이너의 환경변수에 들어간다. 비워 두면 13F 투자자 비교만 데모에서 빠진다.

이 위험을 구조적으로 없애는 방법은 데모를 이 PC 밖(호스팅)으로 옮기는 것이다. "한계와 다음 단계"를 본다.

## 로그인

단일 계정 로그인이다. 비밀번호는 직접 정하고, 해시만 설정 파일에 들어간다.

```powershell
cd backend
py -3.11 -m uv run python -m app.security.hash_password     # 비밀번호를 두 번 묻고 해시 한 줄을 출력
```

출력된 해시를 `backend/.env`의 `AM_AUTH_PASSWORD_HASH='...'`(작은따옴표)에, 32바이트 이상의 무작위 값을 `AM_SESSION_SECRET`에 적는다(`backend/.env.example`에 만드는 명령이 있다). 둘 다 있으면 로그인하지 않은 `/api` 요청은 401이 된다. `AM_ENV=production`으로 실행하면 데모 모드이거나 로그인이 설정돼 있지 않은 한 서버가 시작을 거부한다.

설정을 바꾼 뒤에는 서버를 다시 띄운다(`.\scripts\dev-backend.ps1`). 그 뒤로는 브라우저에서 비밀번호를 한 번 입력해야 화면이 열리고, 로그인은 기본 7일 유지된다.

- 비밀번호를 5번 틀리면 15분 동안 잠긴다. 기다리거나 서버를 다시 띄우면 풀린다.
- 해시나 `AM_SESSION_SECRET`을 바꾸면 모든 브라우저가 로그아웃된다.
- 개발 실행(`AM_ENV=development`)에서는 로그인을 켜도 API 문서(`/docs`, `/openapi.json`)는 열려 있다. 공개 저장소에 있는 내용이라 장부 데이터는 아니다. `AM_ENV=production`에서는 닫힌다.

실제 장부를 인터넷에 여는 것은 이 문서의 범위가 아니다. 그렇게 하려면 로그인을 켠 별도 인스턴스와 별도 터널이 필요하고, 그 전에 2단계(아래)의 항목을 먼저 본다.

## 한계와 다음 단계

- **집 PC 의존**: PC가 꺼지면 데모도 꺼지고, 공개 프로세스가 실제 장부와 같은 PC에서 돈다. 항상 떠 있어야 하거나 이 PC와 분리하고 싶으면 호스팅으로 옮긴다(같은 이미지를 그대로 쓴다).
- **시세 출처**: yfinance는 비공식 경로이고 Yahoo 약관은 개인 용도를 전제로 한다. 포트폴리오 데모까지는 이 구성으로 두고, 다른 사람이 가입해 쓰는 서비스로 가려면 정식 시세 공급자로 바꿔야 한다.
- **외부 호출**: 데모는 이 PC의 인터넷 주소로 Yahoo·업비트·SEC·미국 하원 서기국을 부른다. 방문자가 많아도 캐시와 요청 제한이 막아 주지만, 공급자가 주소를 일시 차단하면 실제 앱의 시세도 같이 느려질 수 있다.
- **프로세스 1개**: 요청 제한·로그인 시도 제한·시세 캐시가 프로세스 메모리에 있어 워커를 늘리면 안 된다. 컨테이너를 다시 시작하면 제한 카운터가 초기화된다.
- **2단계(보류)**: 다중 사용자(가입·사용자별 장부), Postgres, 정식 시세 공급자, 이용약관·개인정보 처리방침, 유료화 전 법률 확인. 계획은 `docs/dev/TODO_FOR_ME.md`에 적어 둔다.

투자 조언이 아닙니다. 데모의 숫자는 가짜 장부에 실제 시세를 입힌 예시입니다.
