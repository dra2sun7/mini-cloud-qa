"""볼륨이 연결된 VM 삭제 테스트 (README '결정 테이블', 설계 결정 9·13, 발견 사항 F-005·F-006)

| 볼륨 연결됨 | delete_volumes | VM 결과  | 볼륨 결과             |
|-------------|----------------|----------|-----------------------|
| 아니오      | false          | DELETING | 해당 없음             |
| 아니오      | true           | DELETING | 해당 없음             |
| 예          | false          | DELETING | 자동 해제 → AVAILABLE |
| 예          | true           | DELETING | 함께 DELETING         |
"""

import pytest

from tests.helpers import (
    GONE,
    get_volume,
    make_vm_in_state,
    make_volume_in_state,
    vm_status,
    volume_status,
    wait_for_vm_status,
    wait_for_volume_status,
)


def delete_vm(client, vm_id: int, delete_volumes: bool | None = None):
    """delete_volumes가 None이면 옵션을 아예 보내지 않는다 (기본값 false)."""
    params = {} if delete_volumes is None else {"delete_volumes": str(delete_volumes).lower()}
    return client.delete(f"/vms/{vm_id}", params=params)


# ---------- 결정 테이블 ----------


@pytest.mark.parametrize("delete_volumes", [False, True], ids=["option-off", "option-on"])
def test_vm_without_volume_is_deleted(client, delete_volumes):
    """결정 테이블 1, 2행: 볼륨이 없으면 옵션과 상관없이 VM만 삭제된다."""
    vm_id = make_vm_in_state(client, "STOPPED")

    assert delete_vm(client, vm_id, delete_volumes).status_code == 202
    assert vm_status(client, vm_id) == "DELETING"

    wait_for_vm_status(client, vm_id, GONE)


def test_attached_volume_is_detached_when_option_off(client):
    """결정 테이블 3행: 옵션을 끄면 볼륨은 데이터 보호를 위해 남는다."""
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)

    assert delete_vm(client, vm_id).status_code == 202

    wait_for_vm_status(client, vm_id, GONE)
    volume = get_volume(client, volume_id)
    assert volume is not None, "볼륨이 데이터 보호를 위해 남아 있어야 한다"
    assert volume["status"] == "AVAILABLE"
    assert volume["vm_id"] is None


def test_attached_volume_is_deleted_when_option_on(client):
    """결정 테이블 4행: 옵션을 켜면 볼륨도 함께 삭제된다."""
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)

    assert delete_vm(client, vm_id, delete_volumes=True).status_code == 202

    wait_for_vm_status(client, vm_id, GONE)
    wait_for_volume_status(client, volume_id, GONE)


def test_volume_stays_attached_while_vm_is_deleting(client):
    """VM이 삭제 중인 동안에는 볼륨이 연결된 채로 남고, 해제 요청은 거부된다."""
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)

    assert delete_vm(client, vm_id).status_code == 202

    assert client.post(f"/volumes/{volume_id}/detach").status_code == 409
    assert volume_status(client, volume_id) == "IN_USE"


def test_only_volumes_of_deleted_vm_are_affected(client):
    """옵션을 켜도 삭제되는 VM의 볼륨만 지워지고, 다른 VM의 볼륨은 그대로여야 한다."""
    deleted_vm = make_vm_in_state(client, "STOPPED")
    other_vm = make_vm_in_state(client, "STOPPED")
    deleted_vm_volume = make_volume_in_state(client, "IN_USE", vm_id=deleted_vm)
    other_vm_volume = make_volume_in_state(client, "IN_USE", vm_id=other_vm)

    assert delete_vm(client, deleted_vm, delete_volumes=True).status_code == 202
    wait_for_vm_status(client, deleted_vm, GONE)
    wait_for_volume_status(client, deleted_vm_volume, GONE)

    other = get_volume(client, other_vm_volume)
    assert other["status"] == "IN_USE"
    assert other["vm_id"] == other_vm


# ---------- 설계 결정 13 (F-005): 삭제 중 재요청의 옵션 비교 ----------

# (첫 요청 옵션, 재요청 옵션, 기대 응답 코드)
# None은 옵션을 보내지 않은 것 = false와 같은 요청
REPEATED_DELETES = [
    pytest.param(None, None, 202, id="omit-then-omit"),
    pytest.param(None, False, 202, id="omit-then-false"),
    pytest.param(False, False, 202, id="false-then-false"),
    pytest.param(True, True, 202, id="true-then-true"),
    pytest.param(None, True, 409, id="omit-then-true"),
    pytest.param(False, True, 409, id="false-then-true"),
    pytest.param(True, False, 409, id="true-then-false"),
    pytest.param(True, None, 409, id="true-then-omit"),
]


@pytest.mark.parametrize("first, second, expected_code", REPEATED_DELETES)
def test_repeated_delete_compares_option(client, first, second, expected_code):
    vm_id = make_vm_in_state(client, "STOPPED")
    assert delete_vm(client, vm_id, first).status_code == 202

    r = delete_vm(client, vm_id, second)

    assert r.status_code == expected_code, r.text
    assert vm_status(client, vm_id) == "DELETING"


def test_conflicting_delete_message_shows_current_option(client):
    vm_id = make_vm_in_state(client, "STOPPED")
    delete_vm(client, vm_id)

    r = delete_vm(client, vm_id, delete_volumes=True)

    assert "delete_volumes=false" in r.json()["detail"]


def test_conflicting_delete_does_not_change_option(client):
    """409로 거부된 재요청은 첫 요청의 옵션을 바꾸지 않는다 → 볼륨은 남아야 한다."""
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)
    delete_vm(client, vm_id)

    assert delete_vm(client, vm_id, delete_volumes=True).status_code == 409

    wait_for_vm_status(client, vm_id, GONE)
    assert volume_status(client, volume_id) == "AVAILABLE"


# ---------- F-006 회귀 테스트 ----------


def test_delete_option_is_kept_across_requests(client):
    """F-006: delete_volumes 값이 DB에 저장되지 않으면 두 번째 요청에서 500이 났다.
    같은 옵션으로 재요청했을 때 202가 나오고, 옵션대로 볼륨이 삭제되는지 확인한다."""
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)
    assert delete_vm(client, vm_id, delete_volumes=True).status_code == 202

    r = delete_vm(client, vm_id, delete_volumes=True)

    assert r.status_code == 202, r.text
    wait_for_vm_status(client, vm_id, GONE)
    wait_for_volume_status(client, volume_id, GONE)
    