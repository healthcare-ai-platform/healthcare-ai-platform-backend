import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import INVITE_EXPIRE_HOURS
from app.db.session import db

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AcceptInviteRequest(BaseModel):
    token: str
    new_password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    user = await db.fetch_one(
        """
        SELECT user_id, tenant_id, facility_id, role, name, password_hash, status
        FROM users
        WHERE email = :email
        """,
        {"email": body.email},
    )
    if not user or user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(body.password, user["password_hash"] or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    payload = _build_payload(user)
    await _write_audit(
        tenant_id=str(user["tenant_id"]),
        user_id=str(user["user_id"]),
        action="login",
        resource="auth",
        ip=_client_ip(request),
    )
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post("/accept-invite", response_model=TokenResponse)
async def accept_invite(body: AcceptInviteRequest, request: Request) -> TokenResponse:
    invite = await db.fetch_one(
        """
        SELECT invite_id, user_id, tenant_id, used_at,
               expires_at < NOW() AS is_expired
        FROM invites
        WHERE token = :token
        """,
        {"token": body.token},
    )
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid invite token")
    if invite["used_at"]:
        raise HTTPException(status_code=400, detail="Invite already used")
    if invite["is_expired"]:
        raise HTTPException(status_code=400, detail="Invite expired")

    pw_hash = hash_password(body.new_password)
    await db.execute(
        "UPDATE users SET status = 'active', password_hash = :pw WHERE user_id = :uid",
        {"pw": pw_hash, "uid": str(invite["user_id"])},
    )
    await db.execute(
        "UPDATE invites SET used_at = NOW() WHERE invite_id = :iid",
        {"iid": str(invite["invite_id"])},
    )

    user = await db.fetch_one(
        "SELECT user_id, tenant_id, facility_id, role, name FROM users WHERE user_id = :uid",
        {"uid": str(invite["user_id"])},
    )
    payload = _build_payload(user)
    await _write_audit(
        tenant_id=str(user["tenant_id"]),
        user_id=str(user["user_id"]),
        action="accept_invite",
        resource="auth",
        ip=_client_ip(request),
    )
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post("/logout", status_code=204)
async def logout() -> None:
    # JWT is stateless — the client discards the token.
    pass


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    row = await db.fetch_one(
        """
        SELECT u.user_id::text, u.name, u.email, u.role, u.status,
               u.created_at, f.name AS facility_name
        FROM users u
        LEFT JOIN facilities f ON f.facility_id = u.facility_id
        WHERE u.user_id = :uid
        """,
        {"uid": current_user["user_id"]},
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    logs = await db.fetch_all(
        """
        SELECT log_id::text AS id, action, resource,
               COALESCE(ip_address::text, '') AS ip,
               created_at
        FROM audit_logs
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 6
        """,
        {"uid": current_user["user_id"]},
    )

    r = dict(row)
    r["created_at"] = row["created_at"].isoformat() if row["created_at"] else None
    r["recent_activity"] = [
        {
            "id":       log["id"],
            "action":   log["action"],
            "resource": log["resource"],
            "ip":       log["ip"],
            "time":     log["created_at"].isoformat() if log["created_at"] else None,
        }
        for log in logs
    ]
    return r


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_payload(user) -> dict:
    return {
        "sub":         str(user["user_id"]),
        "user_id":     str(user["user_id"]),
        "tenant_id":   str(user["tenant_id"]),
        "facility_id": str(user["facility_id"]) if user["facility_id"] else None,
        "role":        user["role"],
        "name":        user["name"],
    }


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _write_audit(
    tenant_id: str, user_id: str, action: str, resource: str, ip: str | None
) -> None:
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
