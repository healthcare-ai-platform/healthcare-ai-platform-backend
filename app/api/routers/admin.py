import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.schemas import Page
from app.core.config import INVITE_EXPIRE_HOURS
from app.core.permissions import require_roles
from app.db.session import db
from app.services.email_service import send_invite_email

router = APIRouter()

_require_platform_admin = require_roles("platform_admin")


# ── Schemas ───────────────────────────────────────────────────────────────────

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


class InviteAdminRequest(BaseModel):
    name: str
    email: str


class AuditLog(BaseModel):
    id: str
    user: str
    action: str
    resource: str
    ip: str
    time: str
    tenant: str


# ── Tenants ───────────────────────────────────────────────────────────────────

@router.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    current_user: dict = Depends(_require_platform_admin),
) -> TenantResponse:
    tenant_row = await db.fetch_one(
        """
        INSERT INTO tenants (name, plan)
        VALUES (:name, :plan)
        RETURNING tenant_id::text AS tenant_id, name, plan, status
        """,
        {"name": body.org_name, "plan": body.plan},
    )
    tenant_id = tenant_row["tenant_id"]

    user_row = await db.fetch_one(
        """
        INSERT INTO users (tenant_id, name, email, role, status)
        VALUES (:tenant_id, :name, :email, 'tenant_admin', 'invited')
        RETURNING user_id::text AS user_id
        """,
        {"tenant_id": tenant_id, "name": body.admin_name, "email": body.admin_email},
    )
    user_id = user_row["user_id"]

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRE_HOURS)
    await db.execute(
        """
        INSERT INTO invites (user_id, tenant_id, token, expires_at)
        VALUES (:user_id, :tenant_id, :token, :expires_at)
        """,
        {"user_id": user_id, "tenant_id": tenant_id, "token": token, "expires_at": expires_at},
    )

    send_invite_email(body.admin_email, body.admin_name, token, "tenant_admin")

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
    current_user: dict = Depends(_require_platform_admin),
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
    current_user: dict = Depends(_require_platform_admin),
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


@router.put("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: str,
    request: Request,
    current_user: dict = Depends(_require_platform_admin),
) -> dict:
    row = await db.fetch_one(
        "SELECT tenant_id FROM tenants WHERE tenant_id = :id",
        {"id": tenant_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.execute(
        "UPDATE tenants SET status = 'suspended' WHERE tenant_id = :id",
        {"id": tenant_id},
    )
    await db.execute(
        """
        INSERT INTO audit_logs (tenant_id, user_id, action, resource, ip_address)
        VALUES (:tenant_id, :user_id, 'suspend_tenant', :resource, :ip)
        """,
        {
            "tenant_id": tenant_id,
            "user_id":   current_user["user_id"],
            "resource":  f"tenant:{tenant_id}",
            "ip":        request.client.host if request.client else None,
        },
    )
    return {"tenant_id": tenant_id, "status": "suspended"}


# ── System health ─────────────────────────────────────────────────────────────

@router.get("/system/health")
async def system_health(
    current_user: dict = Depends(_require_platform_admin),
) -> dict:
    summary = await db.fetch_one(
        """
        SELECT
            COUNT(DISTINCT t.tenant_id)                                        AS total_tenants,
            COUNT(d.document_id)                                               AS docs_today,
            COUNT(d.document_id) FILTER (WHERE d.status = 'failed')           AS failed_today,
            COUNT(d.document_id) FILTER (WHERE d.status IN ('received','ocr','extracting')) AS in_progress
        FROM tenants t
        LEFT JOIN documents d
               ON d.tenant_id = t.tenant_id
              AND DATE(d.created_at) = CURRENT_DATE
        """
    )

    status_breakdown = await db.fetch_all(
        """
        SELECT status, COUNT(*)::int AS count
        FROM documents
        WHERE DATE(created_at) = CURRENT_DATE
        GROUP BY status
        """
    )

    per_tenant = await db.fetch_all(
        """
        SELECT
            t.tenant_id::text,
            t.name,
            COUNT(d.document_id)::int                                        AS docs_today,
            COUNT(d.document_id) FILTER (WHERE d.status = 'failed')::int    AS failed,
            COUNT(d.document_id) FILTER (WHERE d.status IN ('received','ocr','extracting'))::int AS in_progress
        FROM tenants t
        LEFT JOIN documents d
               ON d.tenant_id = t.tenant_id
              AND DATE(d.created_at) = CURRENT_DATE
        GROUP BY t.tenant_id, t.name
        ORDER BY docs_today DESC
        """
    )

    return {
        "total_tenants":  summary["total_tenants"],
        "docs_today":     summary["docs_today"] or 0,
        "failed_today":   summary["failed_today"] or 0,
        "in_progress":    summary["in_progress"] or 0,
        "pipeline": {row["status"]: row["count"] for row in status_breakdown},
        "per_tenant": [dict(row) for row in per_tenant],
    }


# ── Billing ───────────────────────────────────────────────────────────────────

@router.get("/billing")
async def billing(
    current_user: dict = Depends(_require_platform_admin),
) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT
            t.tenant_id::text,
            t.name,
            t.plan,
            t.status,
            COUNT(DISTINCT u.user_id)::int                                                AS user_count,
            COUNT(d.document_id)::int                                                     AS docs_total,
            COUNT(d.document_id) FILTER (
                WHERE DATE_TRUNC('month', d.created_at) = DATE_TRUNC('month', NOW())
            )::int                                                                        AS docs_this_month
        FROM tenants t
        LEFT JOIN users u       ON u.tenant_id = t.tenant_id
        LEFT JOIN documents d   ON d.tenant_id = t.tenant_id
        GROUP BY t.tenant_id, t.name, t.plan, t.status
        ORDER BY docs_this_month DESC
        """
    )
    return [dict(row) for row in rows]


# ── Platform-wide audit logs ──────────────────────────────────────────────────

@router.get("/logs", response_model=Page[AuditLog])
async def platform_logs(
    search: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None, description="Filter by specific tenant"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_platform_admin),
) -> Page[AuditLog]:
    rows = await db.fetch_all(
        """
        SELECT
            al.log_id::text                                          AS id,
            u.name                                                   AS username,
            al.action,
            al.resource,
            COALESCE(al.ip_address::text, '')                        AS ip,
            TO_CHAR(al.created_at AT TIME ZONE 'UTC', 'HH12:MI AM') AS time,
            t.name                                                   AS tenant,
            COUNT(*) OVER ()                                         AS total_count
        FROM audit_logs al
        JOIN users u   ON u.user_id   = al.user_id
        JOIN tenants t ON t.tenant_id = al.tenant_id
        WHERE (:tenant_id IS NULL OR al.tenant_id = :tenant_id::uuid)
          AND (:search = '' OR
               u.name    ILIKE '%' || :search || '%' OR
               al.action ILIKE '%' || :search || '%' OR
               t.name    ILIKE '%' || :search || '%')
        ORDER BY al.created_at DESC
        LIMIT :limit OFFSET :offset
        """,
        {
            "tenant_id": tenant_id,
            "search":    search or "",
            "limit":     page_size,
            "offset":    (page - 1) * page_size,
        },
    )

    total = rows[0]["total_count"] if rows else 0
    items = [
        AuditLog(
            id=row["id"],
            user=row["username"],
            action=row["action"],
            resource=row["resource"],
            ip=row["ip"],
            time=row["time"],
            tenant=row["tenant"],
        )
        for row in rows
    ]
    return Page.build(items, total, page, page_size)


# ── Platform admin user management ────────────────────────────────────────────

@router.get("/users")
async def list_admin_users(
    current_user: dict = Depends(_require_platform_admin),
) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT user_id::text, name, email, status, created_at
        FROM users
        WHERE role = 'platform_admin'
        ORDER BY created_at DESC
        """
    )
    return [dict(row) for row in rows]


@router.post("/users/invite", status_code=201)
async def invite_admin_user(
    body: InviteAdminRequest,
    request: Request,
    current_user: dict = Depends(_require_platform_admin),
) -> dict:
    user_row = await db.fetch_one(
        """
        INSERT INTO users (tenant_id, name, email, role, status, invited_by)
        VALUES (:tenant_id, :name, :email, 'platform_admin', 'invited', :invited_by)
        RETURNING user_id::text AS user_id
        """,
        {
            "tenant_id":  current_user["tenant_id"],
            "name":       body.name,
            "email":      body.email,
            "invited_by": current_user["user_id"],
        },
    )
    user_id = user_row["user_id"]

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRE_HOURS)
    await db.execute(
        """
        INSERT INTO invites (user_id, tenant_id, token, expires_at)
        VALUES (:user_id, :tenant_id, :token, :expires_at)
        """,
        {
            "user_id":    user_id,
            "tenant_id":  current_user["tenant_id"],
            "token":      token,
            "expires_at": expires_at,
        },
    )

    send_invite_email(body.email, body.name, token, "platform_admin")

    await db.execute(
        """
        INSERT INTO audit_logs (tenant_id, user_id, action, resource, ip_address)
        VALUES (:tenant_id, :user_id, 'invite_admin', :resource, :ip)
        """,
        {
            "tenant_id": current_user["tenant_id"],
            "user_id":   current_user["user_id"],
            "resource":  f"user:{user_id}",
            "ip":        request.client.host if request.client else None,
        },
    )

    return {"user_id": user_id, "email": body.email, "role": "platform_admin", "status": "invited"}
