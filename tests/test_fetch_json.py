import asyncio
import sys
from types import SimpleNamespace

from app import fetch_json


def test_fetch_json_passes_request_options_as_keywords(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        async def text(self):
            return '{"ok": true}'

    async def fake_fetch(resource, **options):
        captured["resource"] = resource
        captured["options"] = options
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "workers", SimpleNamespace(fetch=fake_fetch))

    result = asyncio.run(
        fetch_json(
            "https://example.test/token",
            method="POST",
            headers={"content-type": "application/x-www-form-urlencoded"},
            body="code=test",
        )
    )

    assert result == {"ok": True}
    assert captured == {
        "resource": "https://example.test/token",
        "options": {
            "method": "POST",
            "headers": {"content-type": "application/x-www-form-urlencoded"},
            "body": "code=test",
        },
    }
