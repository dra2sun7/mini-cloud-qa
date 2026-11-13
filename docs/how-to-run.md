# 실행 방법

## 1. 설치

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## 2. 서비스 실행

```bash
python -m uvicorn service.main:app --reload
```

`http://localhost:8000/docs`에서 API를 직접 호출해 볼 수 있습니다. VM이 `RUNNING`이 되기까지 기본 10초가 걸립니다.

## 3. 테스트 실행

서버를 테스트용 설정(전환 1초, 자동 재시작 없음)으로 띄운 뒤, 다른 터미널에서 실행합니다.

```bash
# 터미널 1
rm -f mini_cloud.db
PROVISION_SECONDS=1 DELETE_SECONDS=1 python -m uvicorn service.main:app

# 터미널 2
pytest -v
```

테스트는 `MINICLOUD_API_URL`(기본값 `http://localhost:8000`)에 떠 있는 서비스를 대상으로 실행됩니다.

## 4. CLI 사용

```bash
mini-cloud vm create --name web-1 --cpu 2 --memory 4
mini-cloud vm list
mini-cloud vm stop 1
mini-cloud volume create --size 10
mini-cloud volume attach 1 --vm 1
mini-cloud vm delete 1 --delete-volumes
```

---

[← README로 돌아가기](../README.md)
