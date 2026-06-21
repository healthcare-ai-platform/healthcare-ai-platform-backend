import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.api.deps import get_current_user

# Matches the seed data in V002__seed_data.sql
SEED_TENANT_ID    = "11111111-0000-0000-0000-000000000001"
SEED_USER_ID      = "33333333-0000-0000-0000-000000000002"
AUTH_HEADER       = {"Authorization": "Bearer test-token"}
ADMIN_AUTH_HEADER = {"Authorization": "Bearer admin-token"}


async def _fake_user():
    return {
        "tenant_id":   SEED_TENANT_ID,
        "user_id":     SEED_USER_ID,
        "role":        "tenant_admin",
        "facility_id": None,
    }


async def _fake_platform_admin():
    return {
        "tenant_id":   SEED_TENANT_ID,
        "user_id":     SEED_USER_ID,
        "role":        "platform_admin",
        "facility_id": None,
    }


def _db_patches():
    """Context managers that prevent real DB connections during unit tests."""
    return (
        patch("app.db.session.db.connect",             new_callable=AsyncMock),
        patch("app.db.session.db.disconnect",          new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.connect",    new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.disconnect", new_callable=AsyncMock),
    )


@pytest_asyncio.fixture
async def client():
    """
    Integration client — requires real postgres (5432) and redshift-local (5433).
    Run: docker compose up -d postgres redshift-local
    """
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def unit_client():
    """
    Unit client — DB connections mocked, auth overridden as tenant_admin.
    """
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user
    with (
        patch("app.db.session.db.connect",             new_callable=AsyncMock),
        patch("app.db.session.db.disconnect",          new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.connect",    new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.disconnect", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def admin_unit_client():
    """
    Unit client — DB connections mocked, auth overridden as platform_admin.
    """
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_platform_admin
    with (
        patch("app.db.session.db.connect",             new_callable=AsyncMock),
        patch("app.db.session.db.disconnect",          new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.connect",    new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.disconnect", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def anon_unit_client():
    """
    Unit client with NO auth override — used to verify missing tokens return 401.
    """
    app = create_app()
    with (
        patch("app.db.session.db.connect",             new_callable=AsyncMock),
        patch("app.db.session.db.disconnect",          new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.connect",    new_callable=AsyncMock),
        patch("app.db.warehouse.warehouse.disconnect", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
