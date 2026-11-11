# deploy/ — 공개 데모 실행 메모

읽기 전용 **데모 인스턴스**를 이 PC의 Docker에서 띄우고 Cloudflare Tunnel로 공개하기 위한 파일이다(DECISIONS.md D-035). 전체 안내는 [`docs/DEPLOY.md`](../docs/DEPLOY.md)를 본다. 여기에는 파일 설명과 명령만 적는다.

## 파일

| 파일 | 역할 |
| --- | --- |
| `../Dockerfile` | 프론트 빌드(node) + 백엔드(python, uv) 단일 이미지. 비루트 사용자, 헬스체크 `GET /api/health`, torch·transformers·lightgbm·pytest·ruff 없음 |
| `../.dockerignore` | 빌드 컨텍스트 허용 목록. `.env`, `*.db*`, `backend/artifacts/`는 들어가지 않는다 |
| `../backend/scripts/entrypoint.sh` | `alembic upgrade head` → 데모 장부가 비어 있으면 `python -m seed.load` → uvicorn 워커 1개 |
| `docker-compose.yml` | `demo`(앱) + `tunnel`(quick) / `tunnel-named`(named). 호스트에는 `127.0.0.1:8010`만 연다 |
| `.env.example` | `deploy/.env`로 복사해 채우는 값(터널 종류·토큰·호스트 이름). `deploy/.env`는 커밋되지 않는다 |

컨테이너가 볼 수 있는 것은 이미지(코드)와 데모 DB가 든 볼륨 `demo-data`뿐이다. 실제 장부(`backend/asset_manager.db`), `backend/.env`, `backend/artifacts/`는 복사도 마운트도 하지 않는다. `docker-compose.yml`에 `env_file`·호스트 경로 마운트를 추가하지 않는다.

## 실행 (PowerShell, 이 폴더에서)

Docker Desktop을 먼저 켠다.

```powershell
cd deploy
Copy-Item .env.example .env        # 처음 한 번
docker compose up -d --build       # .env의 COMPOSE_PROFILES에 따라 터널까지 함께 뜬다
docker compose ps                  # demo가 healthy가 될 때까지 기다린다(첫 실행은 시세를 받느라 보통 1분 안)
docker compose logs -f demo
```

- **quick 터널**(기본, `COMPOSE_PROFILES=quick`): Cloudflare 계정이 필요 없다. 주소는 시작할 때마다 바뀌고 로그에 찍힌다.
  `docker compose logs tunnel` 에서 `https://....trycloudflare.com` 줄을 찾는다.
- **named 터널**(`COMPOSE_PROFILES=named`): Cloudflare Zero Trust에서 터널을 만들고 공개 호스트 이름의 서비스를 `http://demo:8000`으로 지정한 뒤, `.env`에 `TUNNEL_TOKEN`과 `DEMO_HOSTNAME`을 적는다. 토큰은 비밀값이다.
- **터널 없이**(`COMPOSE_PROFILES=` 비움): 이 PC의 `http://127.0.0.1:8010`에서만 열린다. 공개 전에 먼저 이렇게 확인한다.

멈춤과 초기화:

```powershell
docker compose --profile quick --profile named down       # 컨테이너 정지·삭제(데모 DB는 남음)
docker compose --profile quick --profile named down -v    # 데모 DB 볼륨까지 삭제(다음 시작 때 새로 seed)
```

## 확인

```powershell
# 로컬 헬스체크
Invoke-RestMethod http://127.0.0.1:8010/api/health

# 데모는 쓰기를 거부해야 한다(403이 출력되어야 한다, code=demo_read_only)
curl.exe -s -o NUL -w "%{http_code}" -X POST http://127.0.0.1:8010/api/transactions

# 이미지 안에 비밀·DB·모델 파일이 없는지 (아무것도 출력되지 않아야 한다. /root까지 보려고 root로 실행한다)
docker run --rm --user 0 --entrypoint sh asset-manager-demo:local -c "find /app /data /tmp /root /home \( -name '.env*' -o -name '*.db*' -o -name '*.sqlite*' -o -name 'artifacts' \) 2>/dev/null"

# 컨테이너에 호스트 경로가 마운트되지 않았는지
# (Mounts는 Type이 volume인 demo-data 하나, Tmpfs는 /tmp, 포트는 HostIp 127.0.0.1뿐이어야 한다)
docker inspect (docker compose ps -q demo) --format '{{json .Mounts}} {{json .HostConfig.Tmpfs}} {{json .HostConfig.PortBindings}}'
```

빌드 컨텍스트에 무엇이 실리는지 보려면 저장소 루트에서(`.env`, `*.db`, `artifacts`가 목록에 없어야 한다. 실행할 때마다 이름 없는 이미지가 하나 남으니 가끔 `docker image prune`으로 지운다):

```powershell
"FROM python:3.11.18-slim-bookworm`nCOPY . /ctx`nRUN find /ctx -type f | sort" | docker build --no-cache --progress=plain -f - .
```

## 첫 시작이 실패할 때

- **seed 실패**(네트워크 없음·시세 공급자 차단): 데모 장부의 거래 단가는 실제 시세에서 받는다. 받지 못하면 합성 시세로 바꾸지 않고, 빈 데모도 띄우지 않는다. 로그에 이유를 남기고 5분 뒤 종료하며 재시작 정책이 다시 시도한다. 빈 장부로라도 띄우려면 `.env`에 `DEMO_SEED_ON_FAILURE=continue`.
- **`AM_ENV=production needs either AM_DEMO_MODE ...`**: 이미지를 compose 없이 그냥 실행한 경우다. 설정 없이 뜨지 않는 것이 정상이다.
- **주소 범위 겹침**(`Pool overlaps`): `.env`에 `DEMO_SUBNET_PREFIX=172.30.36`처럼 다른 값을 준다.
- **400 Invalid host header**: 접속한 호스트 이름이 `AM_ALLOWED_HOSTS`에 없다. named 터널이면 `DEMO_HOSTNAME`을 확인한다.

## 실제 장부 백업 (터널과 무관)

```powershell
.\scripts\backup-db.ps1                                # → %USERPROFILE%\asset-manager-backups, 최근 14개 유지
.\scripts\backup-db.ps1 -DestDir D:\backups -Keep 30
```

서버가 켜져 있어도 된다(SQLite 온라인 백업, 무결성 검사 후 저장). 백업에는 실제 보유 내역이 들어 있으므로 저장소 안이나 컨테이너가 볼 수 있는 폴더에 두지 않는다.
