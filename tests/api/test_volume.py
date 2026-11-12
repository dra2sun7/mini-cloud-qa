"""볼륨 테스트 (README '볼륨 상태 전이표', 입력값 규칙, 설계 결정 6·7·8·12)"""

import pytest

from tests.helpers import (
    GONE,
    attach,
    create_volume,
    get_volume,
    make_vm_in_state,
    make_volume_in_state,
    volume_status,
)


@pytest.fixture
def stopped_vms(client):
    """연결용 VM 두 대(같은 VM, 다른 VM)를 STOPPED 상태로 준비한다."""
    return make_vm_in_state(client, "STOPPED"), make_vm_in_state(client, "STOPPED")


# ---------- 볼륨 상태 전이표 ----------
# 연결·해제 대상 VM은 STOPPED 상태로 준비한다.

# (볼륨 상태, 동작, 기대 응답 코드, 기대 이후 상태)
VOLUME_TRANSITIONS = [
    ("AVAILABLE", "attach-same", 200, "IN_USE"),
    ("AVAILABLE", "attach-other", 200, "IN_USE"),
    ("AVAILABLE", "detach", 200, "AVAILABLE"),  # 설계 원칙 2
    ("AVAILABLE", "delete", 202, "DELETING"),
    ("IN_USE", "attach-same", 200, "IN_USE"),  # 설계 결정 8
    ("IN_USE", "attach-other", 409, "IN_USE"),  # 설계 결정 8
    ("IN_USE", "detach", 200, "AVAILABLE"),
    ("IN_USE", "delete", 409, "IN_USE"),  # 설계 결정 7
    ("DELETING", "attach-same", 409, "DELETING"),  # 설계 원칙 1
    ("DELETING", "attach-other", 409, "DELETING"),
    ("DELETING", "detach", 409, "DELETING"),
    ("DELETING", "delete", 202, "DELETING"),
    (GONE, "attach-same", 404, GONE),
    (GONE, "attach-other", 404, GONE),
    (GONE, "detach", 404, GONE),
    (GONE, "delete", 404, GONE),
]


def do_volume_action(client, volume_id: int, action: str, same_vm: int, other_vm: int):
    if action == "attach-same":
        return attach(client, volume_id, same_vm)
    if action == "attach-other":
        return attach(client, volume_id, other_vm)
    if action == "detach":
        return client.post(f"/volumes/{volume_id}/detach")
    return client.delete(f"/volumes/{volume_id}")


@pytest.mark.parametrize(
    "state, action, expected_code, expected_state",
    VOLUME_TRANSITIONS,
    ids=[f"{s}-{a}" for s, a, _, _ in VOLUME_TRANSITIONS],
)
def test_volume_state_transition(client, stopped_vms, state, action, expected_code, expected_state):
    same_vm, other_vm = stopped_vms
    volume_id = make_volume_in_state(client, state, vm_id=same_vm)

    r = do_volume_action(client, volume_id, action, same_vm, other_vm)

    assert r.status_code == expected_code, r.text
    assert volume_status(client, volume_id) == expected_state


def test_rejected_attach_keeps_original_vm(client, stopped_vms):
    """다른 VM에 연결하려다 거부되면, 원래 연결은 그대로 남아야 한다."""
    same_vm, other_vm = stopped_vms
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=same_vm)

    assert attach(client, volume_id, other_vm).status_code == 409

    assert get_volume(client, volume_id)["vm_id"] == same_vm


def test_detach_clears_vm_id(client, stopped_vms):
    same_vm, _ = stopped_vms
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=same_vm)

    client.post(f"/volumes/{volume_id}/detach")

    assert get_volume(client, volume_id)["vm_id"] is None


# ---------- 설계 결정 12: 볼륨 응답의 previous_status ----------


@pytest.mark.parametrize(
    "state, action",
    [("AVAILABLE", "attach-same"), ("IN_USE", "attach-same"), ("IN_USE", "detach"), ("DELETING", "delete")],
    ids=["AVAILABLE-attach", "IN_USE-attach", "IN_USE-detach", "DELETING-delete"],
)
def test_volume_action_response_has_previous_status(client, stopped_vms, state, action):
    same_vm, other_vm = stopped_vms
    volume_id = make_volume_in_state(client, state, vm_id=same_vm)

    body = do_volume_action(client, volume_id, action, same_vm, other_vm).json()

    assert body["previous_status"] == state


# ---------- 설계 결정 6: 연결·해제는 VM이 STOPPED일 때만 ----------


@pytest.mark.parametrize("vm_state", ["PENDING", "RUNNING", "DELETING"])
def test_attach_rejected_when_vm_not_stopped(client, vm_state):
    vm_id = make_vm_in_state(client, vm_state)
    volume_id = create_volume(client)["id"]

    assert attach(client, volume_id, vm_id).status_code == 409

    assert volume_status(client, volume_id) == "AVAILABLE"


def test_detach_rejected_when_vm_running(client):
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)
    assert client.post(f"/vms/{vm_id}/start").status_code == 200

    assert client.post(f"/volumes/{volume_id}/detach").status_code == 409

    assert volume_status(client, volume_id) == "IN_USE"


# ---------- 설계 결정 12: 이미 같은 VM에 연결돼 있으면 VM 상태와 상관없이 성공 ----------


def test_reattach_to_same_running_vm_succeeds(client):
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)
    assert client.post(f"/vms/{vm_id}/start").status_code == 200

    r = attach(client, volume_id, vm_id)

    assert r.status_code == 200, r.text
    assert r.json()["previous_status"] == "IN_USE"


# ---------- 존재하지 않는 대상 ----------


def test_attach_to_unknown_vm_returns_404(client):
    volume_id = create_volume(client)["id"]

    assert attach(client, volume_id, 999999999).status_code == 404

    assert volume_status(client, volume_id) == "AVAILABLE"


# ---------- 경계값: 볼륨 크기 (1~1024GB) ----------

SIZE_BOUNDARIES = [(0, 422), (1, 201), (2, 201), (1023, 201), (1024, 201), (1025, 422)]


@pytest.mark.parametrize("size, expected", SIZE_BOUNDARIES, ids=[f"size-{s}" for s, _ in SIZE_BOUNDARIES])
def test_volume_size_boundary(client, size, expected):
    r = client.post("/volumes", json={"size_gb": size})
    assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "size",
    [
        pytest.param(-1, id="negative"),
        pytest.param(1.5, id="decimal"),
        pytest.param("10", id="numeric-string"),  # 설계 결정 4
        pytest.param(10.0, id="integral-float"),  # 설계 결정 4
        pytest.param(True, id="boolean"),  # 설계 결정 4
        pytest.param(None, id="null"),
    ],
)
def test_volume_size_rejects_invalid_types(client, size):
    r = client.post("/volumes", json={"size_gb": size})
    assert r.status_code == 422, r.text
