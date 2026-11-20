import asyncio
import time
from threading import Event

import pytest
from app import security_events
from app.config import Settings
from app.main import create_app
from starlette.requests import Request
from starlette.responses import Response


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_security_event_storage_wait_does_not_block_event_loop(monkeypatch, tmp_path):
    entered = Event()
    release = Event()

    def slow_record(**_kwargs):
        entered.set()
        release.wait(timeout=0.5)

    monkeypatch.setattr(security_events, "_record_event", slow_record)
    application = create_app(Settings(app_env="test", database_path=tmp_path / "events.db"))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/login",
            "headers": [],
            "server": ("testserver", 80),
            "app": application,
        }
    )

    async def call_next(_request):
        return Response(status_code=401)

    task = asyncio.create_task(security_events.log_security_event(request, call_next))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), timeout=2)
        started = time.monotonic()
        await asyncio.sleep(0.02)
        assert time.monotonic() - started < 0.2
    finally:
        release.set()
        assert (await task).status_code == 401
