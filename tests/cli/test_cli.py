"""CLI 테스트

실제 사용자처럼 터미널 명령을 실행하고, 종료 코드와 출력이 기대와 같은지 확인한다.
API 테스트와 별도로 하는 이유: API가 맞게 응답해도, CLI가 옵션을 잘못 넘기거나 출력을 잘못 보여줄 수 있다.

- stdout: 정상 결과(표)가 나오는 곳
- stderr: 에러 메시지가 나오는 곳
- 종료 코드: 0 성공, 1 API 에러, 2 연결 실패
"""

import os
import subprocess
import sys

from tests.helpers import (
    BASE_URL,
    GONE,
    make_vm_in_state,
    make_volume_in_state,
    unique_name,
    vm_status,
    volume_status,
    wait_for_vm_status,
    wait_for_volume_status,
)


def run_cli(*args: str, api_url: str = BASE_URL) -> subprocess.CompletedProcess:
    """mini-cloud 명령을 실행한다. python -m으로 실행해 가상환경 밖의 명령이 끼어들지 않게 한다."""
    env = {**os.environ, "MINICLOUD_API_URL": api_url}
    return subprocess.run(
        [sys.executable, "-m", "service.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def first_cell(output: str) -> str:
    """표 출력의 첫 데이터 줄 첫 칸(id)을 꺼낸다."""
    return output.splitlines()[1].split()[0]


# ---------- 성공 (종료 코드 0) ----------


def test_vm_create_and_list(client):
    name = unique_name("cli")

    created = run_cli("vm", "create", "--name", name, "--cpu", "2", "--memory", "4")
    listed = run_cli("vm", "list")

    assert created.returncode == 0, created.stderr
    assert name in created.stdout
    assert "PENDING" in created.stdout
    assert listed.returncode == 0, listed.stderr
    assert name in listed.stdout


def test_vm_stop_shows_previous_status(client):
    vm_id = make_vm_in_state(client, "RUNNING")

    first = run_cli("vm", "stop", str(vm_id))
    second = run_cli("vm", "stop", str(vm_id))

    assert first.returncode == 0, first.stderr
    assert "PREVIOUS_STATUS" in first.stdout
    assert first.stdout.splitlines()[1].split()[-2:] == ["STOPPED", "RUNNING"]
    assert second.returncode == 0, second.stderr
    assert second.stdout.splitlines()[1].split()[-2:] == ["STOPPED", "STOPPED"]


def test_volume_create_attach_detach(client):
    vm_id = make_vm_in_state(client, "STOPPED")

    created = run_cli("volume", "create", "--size", "10")
    volume_id = first_cell(created.stdout)
    attached = run_cli("volume", "attach", volume_id, "--vm", str(vm_id))
    detached = run_cli("volume", "detach", volume_id)

    assert created.returncode == 0, created.stderr
    assert attached.returncode == 0, attached.stderr
    assert "IN_USE" in attached.stdout
    assert detached.returncode == 0, detached.stderr
    assert "AVAILABLE" in detached.stdout


def test_vm_delete_with_delete_volumes_option(client):
    """CLI의 --delete-volumes가 API에 true로 전달되는지 확인한다 (F-006 때 수동으로 실패했던 항목)."""
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)

    result = run_cli("vm", "delete", str(vm_id), "--delete-volumes")

    assert result.returncode == 0, result.stderr
    wait_for_vm_status(client, vm_id, GONE)
    wait_for_volume_status(client, volume_id, GONE)


def test_vm_delete_without_option_keeps_volume(client):
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)

    result = run_cli("vm", "delete", str(vm_id))

    assert result.returncode == 0, result.stderr
    wait_for_vm_status(client, vm_id, GONE)
    assert volume_status(client, volume_id) == "AVAILABLE"


# ---------- API 에러 (종료 코드 1) ----------


def test_conflict_shows_409_on_stderr(client):
    vm_id = make_vm_in_state(client, "PENDING")

    result = run_cli("vm", "start", str(vm_id))

    assert result.returncode == 1
    assert "Error 409" in result.stderr
    assert result.stdout == "", "에러는 stdout이 아니라 stderr에 나와야 한다"
    assert vm_status(client, vm_id) == "PENDING"


def test_invalid_input_shows_422(client):
    result = run_cli("vm", "create", "--name", unique_name("cli"), "--cpu", "2", "--memory", "65")

    assert result.returncode == 1
    assert "Error 422" in result.stderr


def test_unknown_vm_shows_404(client):
    result = run_cli("vm", "get", "999999999")

    assert result.returncode == 1
    assert "Error 404" in result.stderr


def test_volume_delete_in_use_shows_409(client):
    vm_id = make_vm_in_state(client, "STOPPED")
    volume_id = make_volume_in_state(client, "IN_USE", vm_id=vm_id)

    result = run_cli("volume", "delete", str(volume_id))

    assert result.returncode == 1
    assert "Detach it first" in result.stderr


# ---------- 연결 실패 (종료 코드 2) ----------


def test_cannot_connect_to_server():
    """서버가 없는 주소로 요청하면 종료 코드 2. 서버가 필요 없어서 client를 쓰지 않는다."""
    result = run_cli("vm", "list", api_url="http://127.0.0.1:1")

    assert result.returncode == 2
    assert "cannot connect" in result.stderr
    