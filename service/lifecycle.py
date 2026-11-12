"""시간이 지나면 자동으로 일어나는 상태 전환을 처리한다.

실제 클라우드라면 백그라운드 작업이 VM 생성·삭제를 진행하지만,
이 프로젝트는 단순하게 만들기 위해 요청이 들어올 때마다
'지금까지 끝났어야 하는 전환'을 한꺼번에 반영한다.

- PENDING VM: PROVISION_SECONDS가 지나면 RUNNING
- DELETING VM: DELETE_SECONDS가 지나면 사라짐
  - 연결된 볼륨은 delete_volumes 옵션에 따라
    자동 해제(AVAILABLE)되거나 함께 DELETING이 된다 (설계 결정 9)
- DELETING 볼륨: DELETE_SECONDS가 지나면 사라짐
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DELETE_SECONDS, PROVISION_SECONDS
from .models import (
    VM,
    VM_DELETING,
    VM_PENDING,
    VM_RUNNING,
    VOL_AVAILABLE,
    VOL_DELETING,
    Volume,
)


def reconcile(session: Session) -> None:
    now = time.time()
    changed = False

    # 1. 생성이 끝났어야 하는 VM은 RUNNING으로
    for vm in session.scalars(select(VM).where(VM.status == VM_PENDING)).all():
        done_at = vm.status_changed_at + PROVISION_SECONDS
        if now >= done_at:
            vm.status = VM_RUNNING
            vm.status_changed_at = done_at  # 실제로 전환됐어야 하는 시각을 기록
            changed = True

    # 2. 삭제가 끝났어야 하는 VM은 연결된 볼륨을 정리하고 DB에서 제거
    for vm in session.scalars(select(VM).where(VM.status == VM_DELETING)).all():
        done_at = vm.status_changed_at + DELETE_SECONDS
        if now < done_at:
            continue
        for vol in session.scalars(select(Volume).where(Volume.vm_id == vm.id)).all():
            vol.vm_id = None
            vol.status = VOL_DELETING if vm.delete_volumes else VOL_AVAILABLE
            vol.status_changed_at = done_at
        session.delete(vm)
        changed = True

    # 2번에서 DELETING이 된 볼륨도 3번에서 보이도록 지금까지의 변경을 DB에 반영
    if changed:
        session.flush()
    
    # 2번에서 DELETING이 된 볼륨도 3번에서 보이도록 지금까지의 변경을 DB에 반영
    if changed:
        session.flush()

    # 3. 삭제가 끝났어야 하는 볼륨은 DB에서 제거
    for vol in session.scalars(select(Volume).where(Volume.status == VOL_DELETING)).all():
        if now >= vol.status_changed_at + DELETE_SECONDS:
            session.delete(vol)
            changed = True

    if changed:
        session.commit()
