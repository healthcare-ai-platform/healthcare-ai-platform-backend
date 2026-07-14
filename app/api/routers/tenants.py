import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.schemas import Page
from app.core.config import INVITE_EXPIRE_HOURS
from app.core.permissions import require_roles
from app.db.session import db
from app.services.email_service import send_invite_email

router = APIRouter()

_COLORS = [
    {"color": "#185fa5", "bg": "#e6f1fb"},
    {"color": "#854f0b", "bg": "#faeeda"},
    {"color": "#534ab7", "bg": "#eeedfe"},
    {"color": "#993556", "bg": "#fbeaf0"},
    {"color": "#0f6e56", "bg": "#e6f5f1"},
]

_ALLOWED_INVITE_ROLES = {"manager", "analyst", "doctor"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class Tenant(BaseModel):
    id: str
    initials: str
    name: str
    docs: int
    sla: str
    color: str
    bg: str
    failures: int
    avgTime: str


FACILITY_TYPES = {"hospital", "clinic", "lab", "imaging_center", "pharmacy"}


class CreateFacilityRequest(BaseModel):
    name: str
    type: str
    city: str | None = None
    address: str | None = None


class FacilityResponse(BaseModel):
    facility_id: str
    name: str
    type: str
    city: str | None
    address: str | None


class InviteUserRequest(BaseModel):
    name: str
    email: str
    role: str
    facility_id: str | None = None


# ── Platform-admin view: list all tenants ─────────────────────────────────────

@router.get("/", response_model=Page[Tenant])
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_roles("platform_admin")),
) -> Page[Tenant]:
    rows = await db.fetch_all(
        """
        WITH tenant_stats AS (
            SELECT
                t.tenant_id::text AS id,
                t.name,
                COUNT(d.document_id)::int                                    AS docs,
                COUNT(d.document_id) FILTER (WHERE d.status = 'failed')::int AS failures,
                COALESCE(
                    ROUND(
                        AVG(
                            EXTRACT(EPOCH FROM (d.updated_at - d.created_at)) / 60.0
                        ) FILTER (WHERE d.status = 'loaded')::numeric,
                        1
                    )::text || ' min',
                    'N/A'
                )                                                            AS avg_time
            FROM tenants t
            LEFT JOIN documents d ON d.tenant_id = t.tenant_id
            GROUP BY t.tenant_id, t.name
            ORDER BY docs DESC
        )
        SELECT *, COUNT(*) OVER () AS total_count
        FROM tenant_stats
        LIMIT :limit OFFSET :offset
        """,
        {
            "limit":  page_size,
            "offset": (page - 1) * page_size,
        },
    )

    total = rows[0]["total_count"] if rows else 0
    offset = (page - 1) * page_size
    items = []
    for i, row in enumerate(rows):
        docs = row["docs"] or 0
        failures = row["failures"] or 0
        sla = "risk" if docs > 0 and (failures / docs) > 0.05 else "ok"
        initials = "".join(w[0] for w in row["name"].split()[:2]).upper()
        palette = _COLORS[(offset + i) % len(_COLORS)]
        items.append(
            Tenant(
                id=row["id"],
                initials=initials,
                name=row["name"],
                docs=docs,
                sla=sla,
                color=palette["color"],
                bg=palette["bg"],
                failures=failures,
                avgTime=row["avg_time"],
            )
        )
    return Page.build(items, total, page, page_size)


# ── Facilities ────────────────────────────────────────────────────────────────

@router.post("/{tenant_id}/facilities", response_model=FacilityResponse, status_code=201)
async def create_facility(
    tenant_id: str,
    body: CreateFacilityRequest,
    request: Request,
    current_user: dict = Depends(require_roles("tenant_admin")),
) -> FacilityResponse:
    _assert_own_tenant(current_user, tenant_id)

    if body.type not in FACILITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid facility type '{body.type}'. Allowed: {', '.join(sorted(FACILITY_TYPES))}.",
        )

    row = await db.fetch_one(
        """
        INSERT INTO facilities (tenant_id, name, type, city, address)
        VALUES (:tenant_id, :name, :type, :city, :address)
        RETURNING facility_id::text AS facility_id, name, type, city, address
        """,
        {"tenant_id": tenant_id, "name": body.name, "type": body.type, "city": body.city, "address": body.address},
    )
    await _write_audit(
        tenant_id, current_user["user_id"],
        "create_facility", f"facility:{row['facility_id']}", request,
    )
    return FacilityResponse(**dict(row))


@router.get("/{tenant_id}/facilities", response_model=list[FacilityResponse])
async def list_facilities(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[FacilityResponse]:
    _assert_own_tenant(current_user, tenant_id)

    rows = await db.fetch_all(
        """
        SELECT facility_id::text AS facility_id, name, type, city, address
        FROM facilities
        WHERE tenant_id = :tid
        ORDER BY name
        """,
        {"tid": tenant_id},
    )
    return [FacilityResponse(**dict(row)) for row in rows]


# ── Users ─────────────────────────────────────────────────────────────────────

@router.post("/{tenant_id}/users/invite", status_code=201)
async def invite_user(
    tenant_id: str,
    body: InviteUserRequest,
    request: Request,
    current_user: dict = Depends(require_roles("tenant_admin")),
) -> dict:
    _assert_own_tenant(current_user, tenant_id)

    if body.role not in _ALLOWED_INVITE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(_ALLOWED_INVITE_ROLES))}",
        )

    if body.facility_id:
        facility = await db.fetch_one(
            "SELECT facility_id FROM facilities WHERE facility_id = :fid AND tenant_id = :tid",
            {"fid": body.facility_id, "tid": tenant_id},
        )
        if not facility:
            raise HTTPException(status_code=400, detail="Facility not found in this tenant")

    user_row = await db.fetch_one(
        """
        INSERT INTO users (tenant_id, facility_id, name, email, role, status, invited_by)
        VALUES (:tenant_id, :facility_id, :name, :email, :role, 'invited', :invited_by)
        RETURNING user_id::text AS user_id
        """,
        {
            "tenant_id":   tenant_id,
            "facility_id": body.facility_id,
            "name":        body.name,
            "email":       body.email,
            "role":        body.role,
            "invited_by":  current_user["user_id"],
        },
    )
    user_id = user_row["user_id"]

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=INVITE_EXPIRE_HOURS)
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

    send_invite_email(body.email, body.name, token, body.role)
    await _write_audit(tenant_id, current_user["user_id"], "invite_user", f"user:{user_id}", request)

    return {"user_id": user_id, "email": body.email, "role": body.role, "status": "invited"}


@router.get("/{tenant_id}/users")
async def list_users(
    tenant_id: str,
    current_user: dict = Depends(require_roles("tenant_admin", "manager")),
) -> list[dict]:
    _assert_own_tenant(current_user, tenant_id)

    rows = await db.fetch_all(
        """
        SELECT
            u.user_id::text  AS user_id,
            u.name,
            u.email,
            u.role,
            u.status,
            u.created_at,
            f.name           AS facility_name
        FROM users u
        LEFT JOIN facilities f ON f.facility_id = u.facility_id
        WHERE u.tenant_id = :tid
        ORDER BY u.created_at DESC
        """,
        {"tid": tenant_id},
    )
    result = []
    for row in rows:
        r = dict(row)
        r["created_at"] = row["created_at"].isoformat() if row["created_at"] else None
        result.append(r)
    return result


@router.put("/{tenant_id}/users/{user_id}/suspend")
async def suspend_user(
    tenant_id: str,
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_roles("tenant_admin")),
) -> dict:
    _assert_own_tenant(current_user, tenant_id)

    # tenant_admin cannot suspend another tenant_admin
    await db.execute(
        """
        UPDATE users
        SET status = 'suspended'
        WHERE user_id = :uid
          AND tenant_id = :tid
          AND role != 'tenant_admin'
        """,
        {"uid": user_id, "tid": tenant_id},
    )
    await _write_audit(tenant_id, current_user["user_id"], "suspend_user", f"user:{user_id}", request)
    return {"user_id": user_id, "status": "suspended"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_own_tenant(current_user: dict, tenant_id: str) -> None:
    if current_user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")


async def _write_audit(
    tenant_id: str, user_id: str, action: str, resource: str, request: Request
) -> None:
    ip = request.client.host if request.client else None
    await db.execute(
        """
        INSERT INTO audit_logs (tenant_id, user_id, action, resource, ip_address)
        VALUES (:tenant_id, :user_id, :action, :resource, :ip)
        """,
        {
            "tenant_id": tenant_id,
            "user_id":   user_id,
            "action":    action,
            "resource":  resource,
            "ip":        ip,
        },
    )
