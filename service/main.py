import time
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .lifecycle import reconcile
from .models import (
    VM,
    VM_DELETING,
    VM_PENDING,
    VM_RUNNING,
    VM_STOPPED,
    VOL_AVAILABLE,
    VOL_DELETING,
    VOL_IN_USE,
    Volume,
)
from .schemas import (
    VMActionOut,
    VMCreate,
    VMOut,
    VolumeActionOut,
    VolumeAttach,
    VolumeCreate,
    VolumeOut,
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버가 켜질 때 실행: 없는 테이블을 만든다
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Mini Cloud", lifespan=lifespan)


# ---------- 공통 도구 ----------


def get_session() -> Iterator[Session]:
    """요청 하나마다 DB 세션을 열고, 자동 전환을 반영한 뒤 넘겨준다."""
    with SessionLocal() as session:
        reconcile(session)
        yield session


def get_vm_or_404(session: Session, vm_id: int) -> VM:
    vm = session.get(VM, vm_id)
    if vm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"VM {vm_id} not found")
    return vm


def get_volume_or_404(session: Session, volume_id: int) -> Volume:
    vol = session.get(Volume, volume_id)
    if vol is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Volume {volume_id} not found"
        )
    return vol


def set_status(vm: VM, new_status: str) -> None:
    """상태를 바꾸고, 바뀐 시각을 기록한다."""
    vm.status = new_status
    vm.status_changed_at = time.time()


def action_result(vm: VM, previous_status: str) -> VMActionOut:
    """상태를 바꾸는 API의 응답을 만든다."""
    return VMActionOut(**VMOut.model_validate(vm).model_dump(), previous_status=previous_status)


def volume_action_result(vol: Volume, previous_status: str) -> VolumeActionOut:
    """볼륨 상태를 바꾸는 API의 응답을 만든다."""
    return VolumeActionOut(
        **VolumeOut.model_validate(vol).model_dump(), previous_status=previous_status
    )


def conflict(message: str) -> HTTPException:
    """현재 상태에서 할 수 없는 동작일 때 쓰는 409 에러"""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


# ---------- 운영용 ----------


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- VM ----------


@app.post("/vms", response_model=VMOut, status_code=status.HTTP_201_CREATED)
def create_vm(body: VMCreate, session: Session = Depends(get_session)):
    vm = VM(name=body.name, cpu=body.cpu, memory_gb=body.memory_gb, status=VM_PENDING)
    session.add(vm)
    session.commit()
    return vm


@app.get("/vms", response_model=list[VMOut])
def list_vms(session: Session = Depends(get_session)):
    return session.scalars(select(VM).order_by(VM.id)).all()


@app.get("/vms/{vm_id}", response_model=VMOut)
def get_vm(vm_id: int, session: Session = Depends(get_session)):
    return get_vm_or_404(session, vm_id)


@app.post("/vms/{vm_id}/start", response_model=VMActionOut)
def start_vm(vm_id: int, session: Session = Depends(get_session)):
    vm = get_vm_or_404(session, vm_id)
    previous = vm.status
    # 설계 결정 10: 이미 실행 중이면 아무것도 바꾸지 않고 성공
    if vm.status == VM_RUNNING:                  CI 에러 발생 유도
        return action_result(vm, previous)       CI 에러 발생 유도
    # 허용 목록: STOPPED일 때만 시작할 수 있다
    if vm.status != VM_STOPPED:
        raise conflict(f"VM {vm_id} cannot be started in {vm.status} state")
    set_status(vm, VM_RUNNING)
    session.commit()
    return action_result(vm, previous)


@app.post("/vms/{vm_id}/stop", response_model=VMActionOut)
def stop_vm(vm_id: int, session: Session = Depends(get_session)):
    vm = get_vm_or_404(session, vm_id)
    previous = vm.status
    # 설계 결정 10: 이미 중지돼 있으면 아무것도 바꾸지 않고 성공
    if vm.status == VM_STOPPED:
        return action_result(vm, previous)
    # 허용 목록: RUNNING일 때만 중지할 수 있다
    if vm.status != VM_RUNNING:
        raise conflict(f"VM {vm_id} cannot be stopped in {vm.status} state")
    set_status(vm, VM_STOPPED)
    session.commit()
    return action_result(vm, previous)


@app.delete("/vms/{vm_id}", response_model=VMActionOut, status_code=status.HTTP_202_ACCEPTED)
def delete_vm(vm_id: int, delete_volumes: bool = False, session: Session = Depends(get_session)):
    vm = get_vm_or_404(session, vm_id)
    previous = vm.status
    # 이 검사가 set_status보다 먼저 와야 삭제 시작 시각이 덮어써지지 않는다
    if vm.status == VM_DELETING:
        # 설계 결정 13: 처음과 다른 옵션으로 재요청하면 무시하지 않고 409로 알린다
        if vm.delete_volumes != delete_volumes:
            raise conflict(
                f"VM {vm_id} is already being deleted with delete_volumes={str(vm.delete_volumes).lower()}"
            )
        # 설계 결정 3: 같은 옵션으로 재요청하면 아무것도 바꾸지 않고 202 (멱등성)
        return action_result(vm, previous)
    # 설계 결정 1: PENDING, RUNNING, STOPPED 모두 삭제할 수 있다
    # 설계 결정 9: 연결된 볼륨 처리 방식을 기억해 두고, 삭제가 끝날 때 적용한다
    vm.delete_volumes = delete_volumes
    set_status(vm, VM_DELETING)
    session.commit()
    return action_result(vm, previous)


# ---------- Volumes ----------


@app.post("/volumes", response_model=VolumeOut, status_code=status.HTTP_201_CREATED)
def create_volume(body: VolumeCreate, session: Session = Depends(get_session)):
    vol = Volume(size_gb=body.size_gb, status=VOL_AVAILABLE, vm_id=None)
    session.add(vol)
    session.commit()
    return vol


@app.get("/volumes", response_model=list[VolumeOut])
def list_volumes(session: Session = Depends(get_session)):
    return session.scalars(select(Volume).order_by(Volume.id)).all()


@app.get("/volumes/{volume_id}", response_model=VolumeOut)
def get_volume(volume_id: int, session: Session = Depends(get_session)):
    return get_volume_or_404(session, volume_id)


@app.post("/volumes/{volume_id}/attach", response_model=VolumeActionOut)
def attach_volume(volume_id: int, body: VolumeAttach, session: Session = Depends(get_session)):
    vol = get_volume_or_404(session, volume_id)
    vm = get_vm_or_404(session, body.vm_id)
    previous = vol.status
    # 설계 원칙 1: 삭제 중인 볼륨은 모든 동작을 거부
    if vol.status == VOL_DELETING:
        raise conflict(f"Volume {volume_id} is being deleted")
    if vol.status == VOL_IN_USE:
        # 설계 결정 8: 이미 같은 VM에 연결돼 있으면 성공 (VM 상태와 상관없이, 설계 결정 12)
        if vol.vm_id == vm.id:
            return volume_action_result(vol, previous)
        # 설계 결정 8: 다른 VM에 연결돼 있으면 거부
        raise conflict(f"Volume {volume_id} is already attached to VM {vol.vm_id}")
    # 설계 결정 6: VM이 STOPPED일 때만 연결할 수 있다
    if vm.status != VM_STOPPED:
        raise conflict(f"Volume can be attached only to a STOPPED VM (VM {vm.id} is {vm.status})")
    vol.vm_id = vm.id
    set_status(vol, VOL_IN_USE)
    session.commit()
    return volume_action_result(vol, previous)


@app.post("/volumes/{volume_id}/detach", response_model=VolumeActionOut)
def detach_volume(volume_id: int, session: Session = Depends(get_session)):
    vol = get_volume_or_404(session, volume_id)
    previous = vol.status
    # 설계 원칙 1: 삭제 중인 볼륨은 모든 동작을 거부
    if vol.status == VOL_DELETING:
        raise conflict(f"Volume {volume_id} is being deleted")
    # 설계 원칙 2: 이미 해제돼 있으면 성공
    if vol.status == VOL_AVAILABLE:
        return volume_action_result(vol, previous)
    # 설계 결정 6: 연결된 VM이 STOPPED일 때만 해제할 수 있다 (DELETING인 VM도 여기서 거부)
    vm = get_vm_or_404(session, vol.vm_id)
    if vm.status != VM_STOPPED:
        raise conflict(
            f"Volume can be detached only from a STOPPED VM (VM {vm.id} is {vm.status})"
        )
    vol.vm_id = None
    set_status(vol, VOL_AVAILABLE)
    session.commit()
    return volume_action_result(vol, previous)


@app.delete(
    "/volumes/{volume_id}", response_model=VolumeActionOut, status_code=status.HTTP_202_ACCEPTED
)
def delete_volume(volume_id: int, session: Session = Depends(get_session)):
    vol = get_volume_or_404(session, volume_id)
    previous = vol.status
    # 설계 결정 3과 같은 이유: 이미 삭제 중이면 202 (멱등성)
    if vol.status == VOL_DELETING:
        return volume_action_result(vol, previous)
    # 설계 결정 7: 사용 중인 볼륨은 먼저 해제해야 삭제할 수 있다
    if vol.status == VOL_IN_USE:
        raise conflict(f"Volume {volume_id} is attached to VM {vol.vm_id}. Detach it first")
    set_status(vol, VOL_DELETING)
    session.commit()
    return volume_action_result(vol, previous)
