"""VM 상태 전이 테스트 (README '상태 전이표')

표의 각 칸이 테스트 하나다.
현재 상태의 VM을 준비하고 → 동작을 요청하고 → 응답 코드와 이후 상태가 표와 같은지 확인한다.
"""

import pytest

from tests.helpers import GONE, create_vm, make_vm_in_state, vm_status, wait_for_vm_status

# 상태 전이표: (현재 상태, 동작, 기대 응답 코드, 기대 이후 상태)
TRANSITIONS = [
    ("PENDING", "start", 409, "PENDING"),
    ("PENDING", "stop", 409, "PENDING"),
    ("PENDING", "delete", 202, "DELETING"),  # 설계 결정 1
    ("RUNNING", "start", 200, "RUNNING"),  # 설계 결정 10
    ("RUNNING", "stop", 200, "STOPPED"),
    ("RUNNING", "delete", 202, "DELETING"),
    ("STOPPED", "start", 200, "RUNNING"),
    ("STOPPED", "stop", 200, "STOPPED"),  # 설계 결정 10
    ("STOPPED", "delete", 202, "DELETING"),
    ("DELETING", "start", 409, "DELETING"),
    ("DELETING", "stop", 409, "DELETING"),
    ("DELETING", "delete", 202, "DELETING"),  # 설계 결정 3
    (GONE, "start", 404, GONE),
    (GONE, "stop", 404, GONE),
    (GONE, "delete", 404, GONE),
]


def do_action(client, vm_id: int, action: str):
    if action == "delete":
        return client.delete(f"/vms/{vm_id}")
    return client.post(f"/vms/{vm_id}/{action}")


@pytest.mark.parametrize(
    "state, action, expected_code, expected_state",
    TRANSITIONS,
    ids=[f"{s}-{a}" for s, a, _, _ in TRANSITIONS],
)
def test_vm_state_transition(client, state, action, expected_code, expected_state):
    vm_id = make_vm_in_state(client, state)

    response = do_action(client, vm_id, action)

    assert response.status_code == expected_code, response.text
    assert vm_status(client, vm_id) == expected_state


# ---------- 설계 결정 11: previous_status ----------


@pytest.mark.parametrize(
    "state, action",
    [("RUNNING", "start"), ("STOPPED", "start"), ("RUNNING", "delete"), ("DELETING", "delete")],
    ids=["RUNNING-start", "STOPPED-start", "RUNNING-delete", "DELETING-delete"],
)
def test_action_response_has_previous_status(client, state, action):
    vm_id = make_vm_in_state(client, state)

    body = do_action(client, vm_id, action).json()

    assert body["previous_status"] == state


def test_rejected_and_get_responses_have_no_previous_status(client):
    vm_id = make_vm_in_state(client, "PENDING")

    rejected = client.post(f"/vms/{vm_id}/start")
    fetched = client.get(f"/vms/{vm_id}")

    assert rejected.status_code == 409
    assert "previous_status" not in rejected.json()
    assert "previous_status" not in fetched.json()


# ---------- 자동 상태 전환 (6단계) ----------


def test_pending_vm_becomes_running_automatically(client):
    vm = create_vm(client)
    assert vm["status"] == "PENDING"

    wait_for_vm_status(client, vm["id"], "RUNNING")


def test_deleting_vm_disappears_automatically(client):
    vm_id = make_vm_in_state(client, "DELETING")

    wait_for_vm_status(client, vm_id, GONE)


# ---------- 발견 사항 ----------


@pytest.mark.xfail(reason="F-004: SQLite에서 삭제된 id가 재사용됨. PostgreSQL 환경에서 검증 예정")
def test_deleted_vm_id_is_not_reused(client):
    old_id = make_vm_in_state(client, GONE)

    new_id = create_vm(client)["id"]

    assert new_id != old_id
    # 예전 VM에 대한 삭제 재시도가 새 VM에 영향을 주면 안 된다
    assert client.delete(f"/vms/{old_id}").status_code == 404
