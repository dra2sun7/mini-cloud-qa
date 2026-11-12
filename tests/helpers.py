"""테스트에서 공통으로 쓰는 도우미 함수

상태 전이 테스트는 '이 상태에서 이 동작을 하면?'을 확인한다.
그래서 먼저 VM을 원하는 상태로 정확히 준비하는 함수가 핵심이다.
"""

import os
import time
import uuid

import httpx

# 테스트할 API 서버 주소
BASE_URL = os.getenv("MINICLOUD_API_URL", "http://localhost:8000")

# 상태가 바뀌기를 기다리는 최대 시간(초)
STATE_TIMEOUT = float(os.getenv("STATE_TIMEOUT", "30"))

# 삭제가 끝나 사라진 상태를 나타내는 테스트용 표기 (API에는 없는 값)
GONE = "GONE"


def unique_name(prefix: str = "vm") -> str:
    """테스트끼리 이름이 겹치지 않게 무작위 이름을 만든다."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def valid_vm_payload(**overrides) -> dict:
    """정상 VM 생성 값. 테스트하고 싶은 칸만 바꿔서 쓴다."""
    payload = {"name": unique_name(), "cpu": 2, "memory_gb": 4}
    payload.update(overrides)
    return payload


def wait_until(condition, timeout: float = STATE_TIMEOUT, interval: float = 0.2, message: str = ""):
    """condition()이 참이 될 때까지 기다린다. 시간 안에 안 되면 테스트를 실패시킨다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise AssertionError(f"{timeout}초 안에 조건을 만족하지 못함: {message}")


# ---------- VM ----------


def create_vm(client: httpx.Client, **overrides) -> dict:
    r = client.post("/vms", json=valid_vm_payload(**overrides))
    assert r.status_code == 201, r.text
    return r.json()


def vm_status(client: httpx.Client, vm_id: int) -> str:
    """VM의 현재 상태. 사라졌으면 GONE."""
    r = client.get(f"/vms/{vm_id}")
    if r.status_code == 404:
        return GONE
    assert r.status_code == 200, r.text
    return r.json()["status"]


def wait_for_vm_status(client: httpx.Client, vm_id: int, expected: str) -> None:
    wait_until(
        lambda: vm_status(client, vm_id) == expected,
        message=f"VM {vm_id}이 {expected} 상태가 되지 않음",
    )


def make_vm_in_state(client: httpx.Client, state: str) -> int:
    """원하는 상태의 VM을 만들어 id를 돌려준다."""
    vm_id = create_vm(client)["id"]
    if state == "PENDING":
        return vm_id

    wait_for_vm_status(client, vm_id, "RUNNING")
    if state == "RUNNING":
        return vm_id

    if state == "STOPPED":
        assert client.post(f"/vms/{vm_id}/stop").status_code == 200
        return vm_id

    assert client.delete(f"/vms/{vm_id}").status_code == 202
    if state == "DELETING":
        return vm_id

    if state == GONE:
        wait_for_vm_status(client, vm_id, GONE)
        return vm_id

    raise ValueError(f"알 수 없는 VM 상태: {state}")


# ---------- 볼륨 ----------


def create_volume(client: httpx.Client, size_gb: int = 10) -> dict:
    r = client.post("/volumes", json={"size_gb": size_gb})
    assert r.status_code == 201, r.text
    return r.json()


def get_volume(client: httpx.Client, volume_id: int) -> dict | None:
    """볼륨 정보. 사라졌으면 None."""
    r = client.get(f"/volumes/{volume_id}")
    if r.status_code == 404:
        return None
    assert r.status_code == 200, r.text
    return r.json()


def volume_status(client: httpx.Client, volume_id: int) -> str:
    """볼륨의 현재 상태. 사라졌으면 GONE."""
    vol = get_volume(client, volume_id)
    return GONE if vol is None else vol["status"]


def wait_for_volume_status(client: httpx.Client, volume_id: int, expected: str) -> None:
    wait_until(
        lambda: volume_status(client, volume_id) == expected,
        message=f"볼륨 {volume_id}이 {expected} 상태가 되지 않음",
    )


def attach(client: httpx.Client, volume_id: int, vm_id: int) -> httpx.Response:
    return client.post(f"/volumes/{volume_id}/attach", json={"vm_id": vm_id})


def make_volume_in_state(client: httpx.Client, state: str, vm_id: int | None = None) -> int:
    """원하는 상태의 볼륨을 만들어 id를 돌려준다. IN_USE면 vm_id(STOPPED VM)에 연결한다."""
    volume_id = create_volume(client)["id"]
    if state == "AVAILABLE":
        return volume_id

    if state == "IN_USE":
        assert vm_id is not None, "IN_USE 볼륨을 만들려면 연결할 VM이 필요하다"
        assert attach(client, volume_id, vm_id).status_code == 200
        return volume_id

    assert client.delete(f"/volumes/{volume_id}").status_code == 202
    if state == "DELETING":
        return volume_id

    if state == GONE:
        wait_for_volume_status(client, volume_id, GONE)
        return volume_id

    raise ValueError(f"알 수 없는 볼륨 상태: {state}")
