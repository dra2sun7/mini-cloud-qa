from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

# SQLite는 여러 요청이 동시에 같은 연결을 쓰는 걸 기본적으로 막아서, 그 제한을 풀어준다.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# engine: DB와 실제로 연결하는 통로
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# SessionLocal: 요청 하나를 처리하는 동안 쓰는 "작업 단위"를 만들어 주는 공장
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Base: 모든 테이블 클래스의 부모. 이걸 상속받은 클래스가 테이블이 된다.
class Base(DeclarativeBase):
    pass
