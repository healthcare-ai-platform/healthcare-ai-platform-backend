"""GET /health — no auth, no DB."""
from tests.conftest import AUTH_HEADER


async def test_health_returns_ok(unit_client):
    r = await unit_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
