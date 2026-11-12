import os

# 데이터베이스 연결 주소.
# 환경 변수 DATABASE_URL이 있으면 그 값을, 없으면 SQLite 파일을 쓴다.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mini_cloud.db")

# PENDING → RUNNING 으로 자동 전환되기까지 걸리는 시간(초)
PROVISION_SECONDS = float(os.getenv("PROVISION_SECONDS", "10"))

# DELETING 상태가 끝나고 VM이 사라지기까지 걸리는 시간(초)
DELETE_SECONDS = float(os.getenv("DELETE_SECONDS", "10"))
