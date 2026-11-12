"""pytest가 모든 테스트 전에 자동으로 읽는 파일

여기 정의한 fixture(테스트 준비물)는 어느 테스트에서든 인자 이름만 적으면 받아 쓸 수 있다.
"""

import httpx
import pytest

from tests.helpers import BASE_URL, wait_until


@pytest.fixture(scope="session")
def client():
    """API 서버와 통신하는 HTTP 클라이언트. 테스트 전체에서 하나를 같이 쓴다."""
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:

        def healthy():
            try:
                return c.get("/health").status_code == 200
            except httpx.HTTPError:
                return False

        # 서버가 안 켜져 있으면 테스트를 시작하지 않고 바로 알려준다
        wait_until(healthy, timeout=10, message=f"{BASE_URL}에 API 서버가 응답하지 않음")
        yield c
        