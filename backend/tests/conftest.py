from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio

_TMP = tempfile.mkdtemp(prefix="w3ex_test_")
os.environ["W3EX_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["W3EX_DEBUG"] = "false"
# 测试必须离线：env 优先级高于 backend/.env，强制 mock provider
os.environ["W3EX_MARKET_PROVIDER"] = "mock"
os.environ["W3EX_EXECUTION_PROVIDER"] = "mock"

from w3ex.config import get_settings  # noqa: E402
from w3ex.db.seed import seed_database  # noqa: E402
from w3ex.db.session import drop_db, get_session_factory, init_db  # noqa: E402
from w3ex.providers.mock.generator import MockDataset  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def _database() -> None:
    get_settings.cache_clear()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await seed_database(session, MockDataset())
    yield
    await drop_db()


@pytest.fixture(autouse=True)
def _reset_circuit():
    """每个测试前清空 HTTP 熔断状态，避免跨测试污染。"""
    from w3ex.providers.http import reset_circuit

    reset_circuit()
    yield
    reset_circuit()


@pytest.fixture
async def session():
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from w3ex.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
