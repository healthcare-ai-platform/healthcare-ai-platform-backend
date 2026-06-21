"""
Auth guard — protected routes must reject requests with no Bearer token.

Uses anon_unit_client (no dependency override) so HTTPBearer actually runs.
Uses unit_client (auth overridden) to confirm valid tokens are accepted.
"""
import pytest
from unittest.mock import patch


PROTECTED_ROUTES = [
    ("GET", "/api/v1/patients/"),
    ("GET", "/api/v1/tenants/"),
    ("GET", "/api/v1/queue/"),
    ("GET", "/api/v1/audit/"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
async def test_missing_token_returns_401(anon_unit_client, method, path):
    # FastAPI's HTTPBearer returns 401 when no Authorization header is present.
    r = await anon_unit_client.request(method, path)
    assert r.status_code == 401, f"{method} {path} should be 401 without token"


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
async def test_bearer_token_accepted(unit_client, method, path):
    """Any non-empty Bearer token passes the stub auth guard."""
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.request(
            method, path, headers={"Authorization": "Bearer any-token"}
        )
        assert r.status_code != 403, f"{method} {path} returned 403 with valid token"
