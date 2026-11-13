# 발견 사항

테스트 중 발견한 결함, 명세 모호, 개선 제안을 기록합니다.
본문의 "설계 원칙", "설계 결정" 번호는 [설계 원칙과 설계 결정](design-decisions.md)을, 상태 전이표와 결정 테이블은 [서비스 명세](spec.md)를 가리킵니다.

## 분류 기준

| 종류 | 의미 |
|---|---|
| **결함** | 명세와 다르게 동작한다 |
| **개선 제안** | 명세대로 동작하지만, 사용성·안정성 등에서 더 나아질 여지가 있다 |
| **명세 모호** | 명세가 정하지 않은 상황이라 동작이 맞는지 판단할 수 없다 |

| 심각도 | 의미 |
|---|---|
| **높음** | 데이터 손실, 잘못된 상태 변경 등 핵심 기능에 영향 |
| **중간** | 기능은 동작하지만 잘못된 결과나 응답을 낸다 |
| **낮음** | 기능에 영향은 없고 사용성·표현의 문제 |

## 목록

| ID | 제목 | 종류 | 심각도 | 상태 |
|---|---|---|---|---|
| F-001 | 이름 형식 오류 메시지에 정규식이 그대로 노출됨 | 개선 제안 | 낮음 | 열림 |
| F-002 | 같은 상태로의 시작·중지 요청이 설계 원칙 2와 충돌 | 명세 모호 | 중간 | 해결 (설계 결정 10) |
| F-003 | 상태 변경 응답만으로 실제로 상태가 바뀌었는지 알 수 없음 | 개선 제안 | 낮음 | 해결 (설계 결정 11) |
| F-004 | 삭제된 VM의 id가 새 VM에 재사용되어, 삭제 재시도가 다른 VM을 삭제함 | 결함 | 높음 | 열림 (PostgreSQL 검증 예정) |
| F-005 | 삭제 중인 VM에 다른 옵션으로 재요청하면 성공 응답과 함께 옵션이 무시됨 | 명세 모호 | 중간 | 해결 (설계 결정 13) |
| F-006 | VM 테이블에 `delete_volumes` 칸이 누락되어 볼륨 정리 실패, 삭제 재요청 시 500 | 결함 | 높음 | 해결 (회귀 테스트 추가) |
| F-007 | VM 조회 결과에 연결된 볼륨이 보이지 않음 | 개선 제안 | 낮음 | 열림 (반영 여부 미정) |

---

## F-001. 이름 형식 오류 메시지에 정규식이 그대로 노출됨

- **종류:** 개선 제안
- **심각도:** 낮음
- **발견일:** 2026-11-10
- **대상:** `POST /vms`, `service/schemas.py`의 `VMName`

### 재현 절차

1. 서버를 실행한다.
2. 아래 본문으로 `POST /vms`를 요청한다.

   ```json
   {"name": "Web_1", "cpu": 2, "memory_gb": 4}
   ```

### 기대 결과

422 응답과 함께, 사용자가 무엇을 고쳐야 하는지 알 수 있는 메시지를 받는다.
예: `이름은 영문 소문자, 숫자, 하이픈(-)만 사용할 수 있고, 하이픈으로 시작하거나 끝날 수 없습니다.`

### 실제 결과

422 응답은 정상이지만, 메시지에 정규식이 그대로 담겨 있다.

```json
{
  "type": "string_pattern_mismatch",
  "loc": ["body", "name"],
  "msg": "String should match pattern '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'",
  "input": "Web_1"
}
```

### 영향

입력 거부 자체는 명세대로 동작하므로 기능 결함은 아니다.
다만 정규식을 읽지 못하는 사용자는 어떤 규칙을 어겼는지 알기 어렵고, 같은 실수를 반복할 수 있다.

### 제안

이름 규칙을 설명하는 메시지를 직접 지정한다. `cpu` 검사처럼 `field_validator`로 바꾸면 메시지를 정할 수 있다.

### 비고

`cpu` 오류의 `ctx` 값이 `{"error": {}}`로 비어 있는 점도 함께 확인했다. 응답 본문에 의미 없는 값이 포함되는 정도라 별도 항목으로 올리지 않았다.

---

## F-002. 같은 상태로의 시작·중지 요청이 설계 원칙 2와 충돌

- **종류:** 명세 모호
- **심각도:** 중간
- **발견일:** 2026-11-10
- **대상:** `POST /vms/{id}/start`, `POST /vms/{id}/stop`, 상태 전이표·설계 원칙 2
- **상태:** 해결 (설계 결정 10)

### 재현 절차

1. VM을 생성하고 DB에서 상태를 `RUNNING`으로 바꾼다.
2. `POST /vms/1/start`를 요청한다.
3. `POST /vms/1/stop`으로 `STOPPED`로 만든 뒤, `POST /vms/1/stop`을 다시 요청한다.

### 실제 결과

상태 전이표대로 두 요청 모두 409를 반환했다.

```json
{"detail": "VM 1 cannot be started in RUNNING state"}
{"detail": "VM 1 cannot be stopped in STOPPED state"}
```

### 문제

구현은 상태 전이표와 일치하지만, **명세 안의 두 규칙이 서로 다른 답을 낸다.**

| 근거 | `RUNNING` VM 시작 | `STOPPED` VM 중지 |
|---|---|---|
| 상태 전이표 | 409 | 409 |
| 설계 원칙 2 ("요청한 결과가 이미 이루어져 있으면 성공") | 200 | 200 |

상태 전이표는 설계 원칙을 만들기 전에 정했고, 원칙 2는 이후 볼륨 재연결과 VM 재삭제를 정하며 일반화했다. 원칙을 만든 뒤 기존 결정을 다시 검토하지 않아 충돌이 남았다.

### 조치

원칙 2를 예외 없이 적용하기로 결정했다 (설계 결정 10).

- 상태 전이표: `RUNNING` / 시작, `STOPPED` / 중지를 409 → 200 (상태 유지)으로 변경
- 코드: `start_vm`, `stop_vm`에서 이미 목표 상태면 아무것도 바꾸지 않고 현재 상태를 반환하도록 수정

### 재확인

- [x] `RUNNING` VM 시작 → 200, 상태 `RUNNING` 유지
- [x] `STOPPED` VM 중지 → 200, 상태 `STOPPED` 유지
- [x] `PENDING`, `DELETING` VM의 시작·중지는 여전히 409

확인일: 2026-11-10 (`/docs`에서 수동 요청)

### 배운 점

설계 원칙을 새로 만들면, 원칙보다 먼저 내린 결정이 원칙과 맞는지 다시 확인해야 한다.

---

## F-003. 상태 변경 응답만으로 실제로 상태가 바뀌었는지 알 수 없음

- **종류:** 개선 제안
- **심각도:** 낮음
- **발견일:** 2026-11-10
- **대상:** `POST /vms/{id}/start`, `POST /vms/{id}/stop`, `DELETE /vms/{id}`
- **상태:** 해결 (설계 결정 11)

### 재현 절차

1. `RUNNING` 상태의 VM을 준비한다.
2. `POST /vms/1/start`를 요청한다.

### 실제 결과

F-002 조치 후 200과 아래 응답을 받는다. `STOPPED` VM을 시작했을 때의 응답과 완전히 같다.

```json
{"id": 1, "name": "1", "cpu": 1, "memory_gb": 1, "status": "RUNNING"}
```

### 영향

명세(설계 결정 10)대로 동작하므로 결함은 아니다. 다만 사용자나 자동화 도구가 "이번 요청으로 VM이 켜졌는지, 원래 켜져 있었는지"를 알 수 없다. 멱등하게 만들면서 생긴 정보 손실이다.

### 조치

시작·중지·삭제 응답에 요청 직전 상태 `previous_status`를 추가했다 (설계 결정 11).

```json
{"id": 1, "name": "1", "cpu": 1, "memory_gb": 1, "status": "RUNNING", "previous_status": "RUNNING"}
```

### 재확인

- [x] `RUNNING` VM 시작 → `previous_status: RUNNING`, `status: RUNNING`
- [x] `STOPPED` VM 시작 → `previous_status: STOPPED`, `status: RUNNING`
- [x] 삭제 재요청 → `previous_status: DELETING`, `status: DELETING`
- [x] `GET /vms/{id}` 응답에는 `previous_status`가 없다
- [x] 409 응답에는 `previous_status`가 없다 (2026-11-10, pytest `test_rejected_and_get_responses_have_no_previous_status` 통과로 확인)

확인일: 2026-11-10 (`/docs`에서 수동 요청)

---

## F-004. 삭제된 VM의 id가 새 VM에 재사용되어, 삭제 재시도가 다른 VM을 삭제함

- **종류:** 결함
- **심각도:** 높음
- **발견일:** 2026-11-10
- **대상:** `service/models.py`의 `VM` 테이블, `DELETE /vms/{id}`
- **환경:** SQLite (로컬 개발 환경)
- **상태:** 열림 (PostgreSQL 환경 검증 예정)
- **직접 재현:** 2026-11-10, SQLite 환경에서 VM 4번을 삭제한 뒤 새로 만든 VM이 다시 4번을 받는 것을 확인. pytest `test_deleted_vm_id_is_not_reused`도 예상대로 `XFAIL`

### 발견 경위

자동 상태 전환(`PENDING → RUNNING`, `DELETING → 삭제 완료`)을 구현한 뒤 확인하던 중, VM 하나를 삭제하고 새 VM을 만든 뒤 `/vms/2`를 요청했더니 404가 나왔다. 새 VM이 2번이 아니라 **1번**으로 만들어져 있었다.

### 재현 절차

1. DB를 초기화하고 서버를 실행한다.
2. VM을 만든다 (`name: old-vm`). → `id: 1`
3. `DELETE /vms/1`을 요청하고, 삭제가 끝날 때까지 기다린다. → `GET /vms/1`이 404
4. VM을 새로 만든다 (`name: new-vm`).
5. 3번의 삭제 요청을 재시도한다고 가정하고, `DELETE /vms/1`을 다시 요청한다.

### 기대 결과

- 4번에서 새 VM은 **사용된 적 없는 id(2)**를 받는다.
- 5번은 이미 사라진 VM에 대한 요청이므로 **404**를 받는다 (설계 결정 3 참고).

### 실제 결과

- 4번에서 새 VM이 **`id: 1`**을 받는다.
- 5번이 **202**를 반환하고, 방금 만든 `new-vm`이 `DELETING`이 된다.

```
A 1 old-vm
A gone 404
B 1 new-vm
retry delete of A id -> 202 new-vm
```

### 원인

SQLite는 `INTEGER PRIMARY KEY`에 `AUTOINCREMENT`가 없으면 **현재 가장 큰 id + 1**을 새 id로 쓴다. 테이블의 마지막 행이 삭제되면 그 id가 다시 쓰인다. 처음 만든 테이블은 SQLAlchemy 기본 설정을 따라 `AUTOINCREMENT`가 없었다.

PostgreSQL의 자동 증가 id는 삭제된 번호를 재사용하지 않으므로, 이 결함은 **SQLite 환경에서만** 나타난다.

### 영향

설계 결정 3은 "네트워크 오류 등으로 삭제를 재시도해도 안전해야 한다"는 이유로 삭제를 멱등하게 만들었다. 그런데 id가 재사용되면 **늦게 도착한 재시도가 전혀 다른 VM을 삭제**한다. 데이터 손실로 이어질 수 있어 심각도를 높음으로 정했다. 설계 원칙 4(데이터 손실 방지)에도 어긋난다.

### 해결 방침

코드를 바꾸지 않고, **서비스가 지원하는 DB를 PostgreSQL로 정하고 PostgreSQL 환경에서 검증**해 해결한다.

- PostgreSQL의 자동 증가 id(시퀀스)는 행이 삭제되어도 번호를 되돌리지 않으므로, 이 결함이 생기지 않아야 한다.
- 테스트 환경(Docker Compose)과 CI도 PostgreSQL을 쓴다.
- SQLite는 Docker 없이 빠르게 확인하는 **개발용으로만** 쓰고, 이 결함을 **알려진 제약**으로 README에 남긴다.

검토한 다른 방안:

| 방안 | 채택하지 않은 이유 |
|---|---|
| SQLite에 `AUTOINCREMENT` 옵션 추가 (`__table_args__ = {"sqlite_autoincrement": True}`) | 개발용 DB만을 위한 설정이 코드에 들어간다. 지원 DB를 PostgreSQL로 정하면 필요 없다 |
| SQLite 지원을 아예 제거 | 로컬에서 빠르게 확인하는 수단이 사라진다 |

### 재확인 (PostgreSQL 환경)

- [ ] 재현 절차 4번에서 새 VM이 `id: 2`를 받는다
- [ ] 재현 절차 5번이 404를 반환하고, `new-vm`은 영향을 받지 않는다
- [x] README와 서비스 명세에 SQLite의 알려진 제약(F-004)을 적었다 (2026-11-13)

### 닫는 조건

위 재확인이 모두 통과하면 상태를 "해결 (PostgreSQL 환경에서 재현되지 않음 확인, SQLite는 알려진 제약)"으로 바꾼다.

### 배운 점

- 같은 코드라도 **DB 종류에 따라 동작이 달라질 수 있다.** 테스트 환경은 운영 환경과 같은 DB를 쓰는 것이 좋다. (Docker Compose로 PostgreSQL 환경을 구성하려는 이유)
- 멱등성 설계는 **"같은 id는 항상 같은 리소스를 가리킨다"**는 전제 위에 있다. 이 전제가 깨지면 재시도 안전성도 함께 깨진다.
- 이 경우를 잡는 테스트("삭제된 id로 다시 요청하면 새 리소스에 영향이 없다")를 자동 테스트에 추가했다 (`test_deleted_vm_id_is_not_reused`, 현재 `XFAIL`).

---

## F-005. 삭제 중인 VM에 다른 옵션으로 재요청하면 성공 응답과 함께 옵션이 무시됨

- **종류:** 명세 모호
- **심각도:** 중간
- **발견일:** 2026-11-10
- **대상:** `DELETE /vms/{id}?delete_volumes=...`, 설계 결정 3·9
- **상태:** 해결 (설계 결정 13, 2026-11-11 재확인)

### 발견 경위

볼륨 API에서 `delete_volumes` 옵션을 구현하던 중, 설계 결정 3("이미 삭제 중이면 아무것도 바꾸지 않고 202")이 옵션이 다른 재요청까지 덮는다는 것을 확인했다.

### 재현 절차

1. `STOPPED` VM에 볼륨을 연결한다.
2. `DELETE /vms/1` (옵션 없음 = `false`)을 요청한다. → 202, `DELETING`
3. 삭제가 끝나기 전에 `DELETE /vms/1?delete_volumes=true`를 요청한다.
4. 삭제가 끝난 뒤 볼륨을 조회한다.

### 실제 결과 (설계 결정 13 이전)

- 3번이 **202**를 반환한다.
- 4번에서 볼륨이 `AVAILABLE`로 남아 있다. 3번의 `delete_volumes=true`는 반영되지 않았다.

### 문제

명세(설계 결정 3)대로 동작하지만, **성공 응답을 받고도 요청한 내용이 적용되지 않는다.** 사용자는 볼륨도 삭제됐다고 생각하고 넘어갈 수 있다.

### 조치

설계 결정 13을 추가하고 `delete_vm`을 수정했다.

- 처음과 같은 옵션으로 재요청 → 202 (기존과 같음, 멱등)
- 처음과 다른 옵션으로 재요청 → **409**, 첫 요청의 옵션 유지

```json
{"detail": "VM 1 is already being deleted with delete_volumes=false"}
```

### 재확인

- [x] 재현 절차 3번이 409를 반환하고, 메시지에 진행 중인 옵션(`false`)이 보인다
- [x] 같은 옵션으로 재요청하면 여전히 202이다 (옵션 생략과 `delete_volumes=false`는 같은 요청으로 취급)
- [x] 삭제가 끝난 뒤 볼륨은 첫 요청 옵션대로 `AVAILABLE`로 남는다
- [x] 반대 방향(`true`로 삭제 → `false`로 재요청)도 409이다

확인일: 2026-11-11 (pytest `test_vm_delete_with_volumes.py`의 옵션 조합 8가지와 메시지·옵션 유지 테스트 통과)

### 배운 점

멱등성 규칙("같은 요청은 몇 번 보내도 같은 결과")에서 **"같은 요청"의 기준**을 분명히 해야 한다. 이번에는 "같은 VM에 대한 삭제"만 같으면 같은 요청으로 봤지만, 실제로는 옵션까지 같아야 같은 요청이다.

---

## F-006. VM 테이블에 `delete_volumes` 칸이 누락되어 볼륨 정리 실패, 삭제 재요청 시 500

- **종류:** 결함 (코드 적용 누락)
- **심각도:** 높음
- **발견일:** 2026-11-11
- **대상:** `service/models.py`의 `VM`, `service/lifecycle.py`, `DELETE /vms/{id}`
- **상태:** 해결 (2026-11-13, CI 전체 통과로 확인)

### 발견 경위

볼륨 API 코드를 적용한 뒤 수동 테스트와 자동 테스트에서 **서로 다른 증상**이 나왔다.

| 확인 방법 | 증상 |
|---|---|
| 수동 (`/docs`, 결정 테이블) | 볼륨이 연결된 VM이 사라져도 볼륨이 `IN_USE`이고 `vm_id`가 남아 있다. `delete_volumes=true`로 삭제해도 볼륨이 지워지지 않는다 |
| 수동 (CLI) | `mini-cloud vm delete <id> --delete-volumes`가 볼륨을 지우지 않는다 |
| 자동 (pytest, VM 상태 전이 테스트) | `test_vm_state_transition[DELETING-delete]`, `test_action_response_has_previous_status[DELETING-delete]`가 **500 Internal Server Error**로 실패 |

### 재현 절차

1. `STOPPED` VM에 볼륨을 연결한다.
2. `DELETE /vms/{id}?delete_volumes=true`를 요청한다. → 202
3. 같은 요청을 한 번 더 보낸다. → **500**
4. 삭제 시간이 지난 뒤 볼륨을 조회한다. → 볼륨이 `IN_USE`, `vm_id`가 그대로 남아 있다

### 기대 결과

- 3번: 202 (설계 결정 3, 13)
- 4번: 볼륨이 `DELETING`이 되었다가 사라진다 (설계 결정 9)

### 원인

볼륨 API용 `models.py`를 적용하면서 `VM` 클래스의 아래 줄이 빠졌다.

```python
delete_volumes: Mapped[bool] = mapped_column(Boolean, default=False)
```

이 칸이 테이블에 없으면,

1. 첫 삭제 요청의 `vm.delete_volumes = True`는 에러 없이 실행되지만 **DB에 저장되지 않는다.** 그 요청 안에서만 값이 존재한다.
2. 두 번째 삭제 요청(새 세션)에서 `vm.delete_volumes`를 읽으려 하면 값이 없어 에러가 나고 500이 된다.
3. 삭제 완료 시점에 `lifecycle.py`가 볼륨 처리 방식을 정하려고 `vm.delete_volumes`를 읽다가 같은 에러로 실패해, 볼륨 정리가 이루어지지 않는다.

세 증상 모두 한 줄 누락에서 나왔다.

> **2026-11-11 추가:** 위 분석은 일부만 맞았다. `models.py`를 고친 뒤 500은 사라졌지만, 결정 테이블 테스트(`test_vm_delete_with_volumes.py`)에서 "VM이 사라져도 볼륨이 `IN_USE`로 남는" 실패 5건이 계속 나왔다. 확인해 보니 **`lifecycle.py`의 VM 삭제 완료 처리도 볼륨 API 이전 버전 그대로**여서, VM을 지우기 전에 볼륨을 정리하는 아래 네 줄이 없었다.
>
> ```python
> for vol in session.scalars(select(Volume).where(Volume.vm_id == vm.id)).all():
>     vol.vm_id = None
>     vol.status = VOL_DELETING if vm.delete_volumes else VOL_AVAILABLE
>     vol.status_changed_at = done_at
> ```
>
> 처음 보고된 "볼륨에 `vm_id`가 남아 있다"는 증상은 사실 이쪽 원인이었다. 개발 환경에서 `lifecycle.py`의 해당 부분만 이전 버전으로 되돌려 실행해, 같은 5건이 같은 이름으로 실패하는 것을 확인했다 (AI 도구로 재현).
>
> | 빠진 곳 | 증상 | 상태 |
> |---|---|---|
> | `models.py`의 `delete_volumes` 칸 | 삭제 재요청 시 500 | 수정 확인 (pytest) |
> | `lifecycle.py`의 볼륨 정리 | VM 삭제 후 볼륨이 정리되지 않음 | 수정 확인 (`test_vm_delete_with_volumes.py`, 17 passed) |
>
> **배운 점 추가:** 증상 여러 개를 원인 하나로 설명하고 싶어지지만, 하나를 고친 뒤 남은 증상이 정말 사라졌는지 다시 확인해야 한다. 이번에는 결정 테이블 회귀 테스트가 남은 원인을 드러냈다.

### 조치

- `models.py`의 `VM`에 `delete_volumes` 칸을 추가했다.
- `lifecycle.py`의 VM 삭제 완료 처리에 볼륨 정리 코드를 추가했다.
- 테이블 모양이 바뀌므로 `mini_cloud.db`를 지우고 다시 만들었다.
- 회귀 테스트 `test_delete_option_is_kept_across_requests`를 추가했다.

### 재확인

- [x] `pytest -v` → 22 passed, 1 xfailed (`DELETING-delete` 500 해소) (2026-11-11, `test_vm_state_transition.py`)
- [x] 옵션 없이 VM 삭제 → 볼륨 `AVAILABLE`, `vm_id: null` (2026-11-11, pytest)
- [x] `delete_volumes=true`로 VM 삭제 → 볼륨이 `DELETING`이 되었다가 사라짐 (2026-11-11, pytest)
- [x] CLI `vm delete <id> --delete-volumes` → 볼륨까지 사라짐 (2026-11-13, GitHub Actions에서 `test_cli.py` 포함 전체 131 passed, 1 xfailed)

### 배운 점

- **수동 테스트와 자동 테스트가 같은 원인을 다른 모습으로 잡았다.** 수동은 "결과가 이상하다", 자동은 "서버 에러"로 드러났다. 증상을 모아 보면 공통 원인을 좁힐 수 있다.
- 실무의 **배포 누락**(일부 파일만 새 버전으로 바뀐 상태)과 같은 유형이다. 여러 파일을 함께 바꾸는 변경은 빠진 파일이 없는지 확인해야 한다.
- 이 상황에서 서비스는 에러 없이 202를 돌려주며 옵션을 잃어버렸다. **"에러가 안 났다"가 "제대로 저장됐다"를 뜻하지 않는다.**

---

## F-007. VM 조회 결과에 연결된 볼륨이 보이지 않음

- **종류:** 개선 제안
- **심각도:** 낮음
- **발견일:** 2026-11-11
- **대상:** `GET /vms`, `GET /vms/{id}`, CLI `vm list`, `vm get`
- **상태:** 열림 (반영 여부 미정)

### 발견 경위

결정 테이블을 수동으로 확인하던 중, VM을 삭제하기 전에 "이 VM에 어떤 볼륨이 붙어 있는지"를 VM 쪽에서 확인할 방법이 없다는 것을 알았다.

### 현재 동작

- 볼륨 조회 결과에는 `vm_id`가 있어, 볼륨 → VM 방향은 확인할 수 있다.
- VM 조회 결과에는 볼륨 정보가 없어, VM → 볼륨 방향은 볼륨 목록 전체를 뒤져야 한다.

```json
{"id": 2, "name": "web-1", "cpu": 2, "memory_gb": 4, "status": "STOPPED"}
```

### 영향

명세에 없는 기능이므로 결함은 아니다. 다만 `delete_volumes` 옵션에 따라 볼륨이 함께 삭제될 수 있는데(설계 결정 9), 사용자가 VM 삭제 전에 영향 범위를 확인하기 어렵다. 설계 원칙 4(데이터 손실 방지)와도 관련이 있다.

### 제안

VM 조회 응답에 연결된 볼륨 id 목록을 추가한다.

```json
{"id": 2, "name": "web-1", "cpu": 2, "memory_gb": 4, "status": "STOPPED", "volume_ids": [1, 3]}
```

CLI `vm list`, `vm get`에도 `VOLUME_IDS` 칸을 추가한다.

---

[← README로 돌아가기](../README.md)
