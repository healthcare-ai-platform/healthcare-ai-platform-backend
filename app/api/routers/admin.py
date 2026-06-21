import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import INVITE_EXPIRE_HOURS
from app.core.permissions import require_roles
from app.db.session import db
from app.services.email_service import send_invite_email

router = APIRouter()


class CreateTenantRequest(BaseModel):
    org_name: str
    plan: str
    admin_name: str
    admin_email: str


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
    plan: str
    status: str


@router.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    current_user: dict = Depends(require_roles("platform_admin")),
) -> TenantResponse:
    # 1. Tenant row
    tenant_row = await db.fetch_one(
        """
        INSERT INTO tenants (name, plan)
        VALUES (:name, :plan)
        RETURNING tenant_id::text AS tenant_id, name, plan, status
        """,
        {"name": body.org_name, "plan": body.plan},
    )
    tenant_id = tenant_row["tenant_id"]

    # 2. tenant_admin user (status=invited, no password yet)
    user_row = await db.fetch_one(
        """
        INSERT INTO users (tenant_id, name, email, role, status)
        VALUES (:tenant_id, :name, :email, 'tenant_admin', 'invited')
        RETURNING user_id::text AS user_id
        """,
        {"tenant_id": tenant_id, "name": body.admin_name, "email": body.admin_email},
    )
    user_id = user_row["user_id"]

    # 3. Invite token (48 hr expiry)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRE_HOURS)
    await db.execute(
        """
        INSERT INTO invites (user_id, tenant_id, token, expires_at)
        VALUES (:user_id, :tenant_id, :token, :expires_at)
        """,
        {
            "user_id":    user_id,
            "tenant_id":  tenant_id,
            "token":      token,
            "expires_at": expires_at,
        },
    )

    # 4. Send invite email (logs invite URL on failure so dev still works)
    send_invite_email(body.admin_email, body.admin_name, token, "tenant_admin")

    # 5. Audit log attributed to the new tenant
    await db.execute(
        """
        INSERT INTO audit_logs (tenant_id, user_id, action, resource, ip_address)
        VALUES (:tenant_id, :user_id, 'create_tenant', :resource, :ip)
        """,
        {
            "tenant_id": tenant_id,
            "user_id":   current_user["user_id"],
            "resource":  f"tenant:{tenant_id}",
            "ip":        request.client.host if request.client else None,
        },
    )

    return TenantResponse(
        tenant_id=tenant_id,
        name=tenant_row["name"],
        plan=tenant_row["plan"],
        status=tenant_row["status"],
    )


@router.get("/tenants")
async def list_tenants_admin(
    current_user: dict = Depends(require_roles("platform_admin")),
) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT tenant_id::text, name, plan, status, created_at
        FROM tenants
        ORDER BY created_at DESC
        """
    )
    return [dict(row) for row in rows]


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    current_user: dict = Depends(require_roles("platform_admin")),
) -> dict:
    row = await db.fetch_one(
        """
        SELECT tenant_id::text, name, plan, status, created_at
        FROM tenants
        WHERE tenant_id = :id
        """,
        {"id": tenant_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return dict(row)
