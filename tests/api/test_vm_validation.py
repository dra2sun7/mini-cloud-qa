"""VM 생성 입력값 테스트 (README '경계값 분석', '동등 분할', 설계 결정 4·5)

check_schema.py에서 손으로 확인하던 것을 pytest로 옮긴 것이다.
check_schema.py는 서비스 코드(VMCreate)를 직접 불렀지만, 이 테스트는 API에 요청을 보내 응답 코드를 확인한다.
"""

import pytest

from tests.helpers import valid_vm_payload

OK = 201
INVALID = 422


def create(client, **overrides):
    return client.post("/vms", json=valid_vm_payload(**overrides))


# ---------- 경계값: 이름 길이 (1~63자) ----------

NAME_LENGTHS = [
    (0, INVALID),  # 최솟값 바로 밖
    (1, OK),  # 최솟값
    (2, OK),  # 최솟값 바로 안
    (62, OK),  # 최댓값 바로 안
    (63, OK),  # 최댓값
    (64, INVALID),  # 최댓값 바로 밖
]


@pytest.mark.parametrize("length, expected", NAME_LENGTHS, ids=[f"len-{n}" for n, _ in NAME_LENGTHS])
def test_name_length_boundary(client, length, expected):
    r = create(client, name="a" * length)
    assert r.status_code == expected, r.text


# ---------- 경계값: 메모리 (1~64GB) ----------

MEMORY_BOUNDARIES = [
    (0, INVALID),  # 최솟값 바로 밖
    (1, OK),  # 최솟값
    (2, OK),  # 최솟값 바로 안
    (63, OK),  # 최댓값 바로 안
    (64, OK),  # 최댓값
    (65, INVALID),  # 최댓값 바로 밖
]


@pytest.mark.parametrize(
    "memory, expected", MEMORY_BOUNDARIES, ids=[f"mem-{m}" for m, _ in MEMORY_BOUNDARIES]
)
def test_memory_boundary(client, memory, expected):
    r = create(client, memory_gb=memory)
    assert r.status_code == expected, r.text


# ---------- 메모리: 잘못된 형식 (설계 결정 4) ----------

MEMORY_INVALID_TYPES = [
    pytest.param(-1, id="negative"),
    pytest.param(1.5, id="decimal"),
    pytest.param("4", id="numeric-string"),  # 설계 결정 4
    pytest.param(4.0, id="integral-float"),  # 설계 결정 4
    pytest.param(True, id="boolean"),  # 설계 결정 4
    pytest.param(None, id="null"),
]


@pytest.mark.parametrize("memory", MEMORY_INVALID_TYPES)
def test_memory_rejects_invalid_types(client, memory):
    r = create(client, memory_gb=memory)
    assert r.status_code == INVALID, r.text


@pytest.mark.parametrize("field", ["name", "cpu", "memory_gb"])
def test_missing_required_field(client, field):
    payload = valid_vm_payload()
    del payload[field]

    r = client.post("/vms", json=payload)

    assert r.status_code == INVALID, r.text


# ---------- 동등 분할: CPU (1, 2, 4, 8만 허용) ----------

CPU_PARTITIONS = [
    pytest.param(2, OK, id="allowed"),
    pytest.param(3, INVALID, id="in-range-not-allowed"),
    pytest.param(16, INVALID, id="above-range"),
    pytest.param(0, INVALID, id="zero-or-less"),
    pytest.param("2", INVALID, id="numeric-string"),  # 설계 결정 4
]


@pytest.mark.parametrize("cpu, expected", CPU_PARTITIONS)
def test_cpu_partitions(client, cpu, expected):
    r = create(client, cpu=cpu)
    assert r.status_code == expected, r.text


@pytest.mark.parametrize("cpu", [1, 2, 4, 8])
def test_all_allowed_cpu_values(client, cpu):
    """허용값이 4개뿐이라 대표값 하나가 아니라 전부 확인한다."""
    r = create(client, cpu=cpu)
    assert r.status_code == OK, r.text


# ---------- 동등 분할: 이름 형식 ----------

NAME_PARTITIONS = [
    pytest.param("web-1", OK, id="normal"),
    pytest.param("123", OK, id="digits-only"),  # 설계 결정 5
    pytest.param("web--1", OK, id="consecutive-hyphens"),  # 설계 결정 5
    pytest.param("-web", INVALID, id="leading-hyphen"),
    pytest.param("web-", INVALID, id="trailing-hyphen"),
    pytest.param("---", INVALID, id="hyphens-only"),
    pytest.param("Web-1", INVALID, id="uppercase"),
    pytest.param("web_1", INVALID, id="underscore"),
    pytest.param("web 1", INVALID, id="space"),
    pytest.param("웹서버", INVALID, id="non-ascii"),
]


@pytest.mark.parametrize("name, expected", NAME_PARTITIONS)
def test_name_partitions(client, name, expected):
    r = create(client, name=name)
    assert r.status_code == expected, r.text


# ---------- 생성 결과 ----------


def test_created_vm_matches_request(client):
    payload = valid_vm_payload(cpu=4, memory_gb=8)

    body = client.post("/vms", json=payload).json()

    assert body["name"] == payload["name"]
    assert body["cpu"] == 4
    assert body["memory_gb"] == 8
    assert body["status"] == "PENDING"


def test_rejected_vm_is_not_created(client):
    """거부된 요청이 DB에 아무것도 남기지 않는지 확인한다."""
    before = len(client.get("/vms").json())

    r = create(client, cpu=3)

    assert r.status_code == INVALID
    assert len(client.get("/vms").json()) == before