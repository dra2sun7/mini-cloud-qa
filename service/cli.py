"""Mini Cloud CLI

터미널에서 Mini Cloud API를 사용하는 명령어 도구.
API 서버 주소는 환경 변수 MINICLOUD_API_URL로 바꿀 수 있다. (기본값: http://localhost:8000)

종료 코드
    0: 성공
    1: API가 에러를 돌려줌 (404, 409, 422 등)
    2: API 서버에 연결할 수 없음

예시
    mini-cloud vm create --name web-1 --cpu 2 --memory 4
    mini-cloud vm list
    mini-cloud vm stop 1
    mini-cloud vm delete 1 --delete-volumes
    mini-cloud volume create --size 10
    mini-cloud volume attach 1 --vm 1
"""

import os

import httpx
import typer

app = typer.Typer(help="Mini Cloud CLI", no_args_is_help=True)
vm_app = typer.Typer(help="VM 관리", no_args_is_help=True)
volume_app = typer.Typer(help="볼륨 관리", no_args_is_help=True)
app.add_typer(vm_app, name="vm")
app.add_typer(volume_app, name="volume")

# 표로 보여줄 칸
VM_COLUMNS = ["id", "name", "cpu", "memory_gb", "status"]
VM_ACTION_COLUMNS = VM_COLUMNS + ["previous_status"]
VOLUME_COLUMNS = ["id", "size_gb", "status", "vm_id"]
VOLUME_ACTION_COLUMNS = VOLUME_COLUMNS + ["previous_status"]


# ---------- 공통 도구 ----------


def api_url() -> str:
    return os.getenv("MINICLOUD_API_URL", "http://localhost:8000").rstrip("/")


def call(method: str, path: str, **kwargs):
    """API를 호출하고, 실패하면 에러 메시지를 출력한 뒤 종료 코드와 함께 끝낸다."""
    try:
        response = httpx.request(method, api_url() + path, timeout=10, **kwargs)
    except httpx.HTTPError as e:
        typer.echo(f"Error: cannot connect to API server at {api_url()} ({e})", err=True)
        raise typer.Exit(code=2)

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text
        typer.echo(f"Error {response.status_code}: {detail}", err=True)
        raise typer.Exit(code=1)

    return response.json()


def print_table(rows: list[dict], columns: list[str]) -> None:
    """딕셔너리 목록을 칸을 맞춘 표로 출력한다. 값이 없으면 '-'로 보여준다."""
    cells = [["-" if row.get(c) is None else str(row[c]) for c in columns] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    typer.echo("  ".join(c.upper().ljust(w) for c, w in zip(columns, widths)))
    for r in cells:
        typer.echo("  ".join(v.ljust(w) for v, w in zip(r, widths)))


# ---------- VM ----------


@vm_app.command("create")
def vm_create(
    name: str = typer.Option(..., help="VM 이름"),
    cpu: int = typer.Option(..., help="CPU 수 (1, 2, 4, 8)"),
    memory: int = typer.Option(..., help="메모리(GB), 1~64"),
):
    """VM을 만든다."""
    vm = call("POST", "/vms", json={"name": name, "cpu": cpu, "memory_gb": memory})
    print_table([vm], VM_COLUMNS)


@vm_app.command("list")
def vm_list():
    """VM 목록을 보여준다."""
    print_table(call("GET", "/vms"), VM_COLUMNS)


@vm_app.command("get")
def vm_get(vm_id: int):
    """VM 하나를 보여준다."""
    print_table([call("GET", f"/vms/{vm_id}")], VM_COLUMNS)


@vm_app.command("start")
def vm_start(vm_id: int):
    """VM을 시작한다."""
    print_table([call("POST", f"/vms/{vm_id}/start")], VM_ACTION_COLUMNS)


@vm_app.command("stop")
def vm_stop(vm_id: int):
    """VM을 중지한다."""
    print_table([call("POST", f"/vms/{vm_id}/stop")], VM_ACTION_COLUMNS)


@vm_app.command("delete")
def vm_delete(
    vm_id: int,
    delete_volumes: bool = typer.Option(
        False, "--delete-volumes", help="연결된 볼륨도 함께 삭제한다"
    ),
):
    """VM을 삭제한다. 기본으로 연결된 볼륨은 남긴다."""
    params = {"delete_volumes": str(delete_volumes).lower()}
    print_table([call("DELETE", f"/vms/{vm_id}", params=params)], VM_ACTION_COLUMNS)


# ---------- 볼륨 ----------


@volume_app.command("create")
def volume_create(size: int = typer.Option(..., help="크기(GB), 1~1024")):
    """볼륨을 만든다."""
    print_table([call("POST", "/volumes", json={"size_gb": size})], VOLUME_COLUMNS)


@volume_app.command("list")
def volume_list():
    """볼륨 목록을 보여준다."""
    print_table(call("GET", "/volumes"), VOLUME_COLUMNS)


@volume_app.command("get")
def volume_get(volume_id: int):
    """볼륨 하나를 보여준다."""
    print_table([call("GET", f"/volumes/{volume_id}")], VOLUME_COLUMNS)


@volume_app.command("attach")
def volume_attach(volume_id: int, vm: int = typer.Option(..., "--vm", help="연결할 VM id")):
    """볼륨을 VM에 연결한다."""
    result = call("POST", f"/volumes/{volume_id}/attach", json={"vm_id": vm})
    print_table([result], VOLUME_ACTION_COLUMNS)


@volume_app.command("detach")
def volume_detach(volume_id: int):
    """볼륨을 VM에서 해제한다."""
    print_table([call("POST", f"/volumes/{volume_id}/detach")], VOLUME_ACTION_COLUMNS)


@volume_app.command("delete")
def volume_delete(volume_id: int):
    """볼륨을 삭제한다."""
    print_table([call("DELETE", f"/volumes/{volume_id}")], VOLUME_ACTION_COLUMNS)


if __name__ == "__main__":
    app()
