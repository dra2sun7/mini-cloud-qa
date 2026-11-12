import time

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# VM 상태 값. 오타를 막으려고 문자열을 직접 쓰지 않고 이 상수를 쓴다.
VM_PENDING = "PENDING"
VM_RUNNING = "RUNNING"
VM_STOPPED = "STOPPED"
VM_DELETING = "DELETING"

# 볼륨 상태 값
VOL_AVAILABLE = "AVAILABLE"
VOL_IN_USE = "IN_USE"
VOL_DELETING = "DELETING"


class VM(Base):
    __tablename__ = "vms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(63))
    cpu: Mapped[int] = mapped_column(Integer)
    memory_gb: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    # 상태가 마지막으로 바뀐 시각(유닉스 시간, 초). 자동 전환 시점을 계산하는 데 쓴다.
    status_changed_at: Mapped[float] = mapped_column(Float, default=time.time)
    # 삭제 요청 때 받은 delete_volumes 옵션. 삭제가 끝날 때 연결된 볼륨을 어떻게 할지 정한다.
    delete_volumes: Mapped[bool] = mapped_column(Boolean, default=False)

class Volume(Base):
    __tablename__ = "volumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    size_gb: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    # 연결된 VM의 id. 연결돼 있지 않으면 None.
    vm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_changed_at: Mapped[float] = mapped_column(Float, default=time.time)
