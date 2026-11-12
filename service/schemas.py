from typing import Annotated
from pydantic import BaseModel, Field, StrictInt, field_validator, ConfigDict

# 이름 규칙: 영문 소문자·숫자·하이픈만, 하이픈으로 시작하거나 끝날 수 없음
NAME_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"

# CPU 허용값
ALLOWED_CPUS = {1, 2, 4, 8}

# 이름: 1~63자 + 위 패턴
VMName = Annotated[str, Field(min_length=1, max_length=63, pattern=NAME_PATTERN)]

# 메모리: 1~64 사이의 "진짜 정수"만 (설계 결정 4)
MemoryGB = Annotated[StrictInt, Field(ge=1, le=64)]

# 볼륨 크기: 1~1024 사이의 "진짜 정수"만 (설계 결정 4)
VolumeSizeGB = Annotated[StrictInt, Field(ge=1, le=1024)]


class VMCreate(BaseModel):
    """VM 생성 요청 때 사용자가 보내는 값"""

    name: VMName
    cpu: StrictInt
    memory_gb: MemoryGB

    @field_validator("cpu")
    @classmethod
    def cpu_must_be_allowed(cls, v: int) -> int:
        if v not in ALLOWED_CPUS:
            raise ValueError(f"cpu must be one of {sorted(ALLOWED_CPUS)}")
        return v

class VMOut(BaseModel):
    """API가 사용자에게 돌려주는 VM 정보"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cpu: int
    memory_gb: int
    status: str
    
class VMActionOut(VMOut):
    """시작·중지·삭제 응답. VMOut에 요청 직전 상태를 더한다."""

    previous_status: str


# ---------- 볼륨 ----------


class VolumeCreate(BaseModel):
    """볼륨 생성 요청 때 사용자가 보내는 값"""

    size_gb: VolumeSizeGB


class VolumeAttach(BaseModel):
    """볼륨 연결 요청 때 사용자가 보내는 값"""

    vm_id: StrictInt


class VolumeOut(BaseModel):
    """API가 사용자에게 돌려주는 볼륨 정보"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    size_gb: int
    status: str
    vm_id: int | None


class VolumeActionOut(VolumeOut):
    """연결·해제·삭제 응답. VolumeOut에 요청 직전 상태를 더한다."""

    previous_status: str
