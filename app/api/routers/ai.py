import asyncio
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.session import db

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


# ── Summary queries (always injected upfront) ─────────────────────────────────

async def _base_stats(tenant_id: str) -> dict:
    row = await db.fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE created_at >= NOW()::date)                        AS docs_today,
            COUNT(*) FILTER (WHERE status = 'failed')                                AS dlq_count,
            COUNT(*) FILTER (WHERE status = 'failed' AND created_at >= NOW()::date)  AS failed_today,
            COUNT(*) FILTER (WHERE status IN ('received','ocr','extracting')
                             AND created_at < NOW() - INTERVAL '30 minutes')         AS stuck_count,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE status = 'loaded' AND created_at >= NOW()::date)
                / NULLIF(COUNT(*) FILTER (WHERE created_at >= NOW()::date), 0)
            , 1)                                                                     AS success_rate,
            COUNT(DISTINCT uploaded_by)                                              AS active_users
        FROM documents
        WHERE tenant_id = :tid
        """,
        {"tid": tenant_id},
    )
    return dict(row)


async def _facility_breakdown(tenant_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT f.name AS facility,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE d.status = 'failed') AS failed
        FROM documents d
        JOIN facilities f ON f.facility_id = d.facility_id
        WHERE d.tenant_id = :tid AND d.created_at >= NOW()::date
        GROUP BY f.name ORDER BY total DESC LIMIT 5
        """,
        {"tid": tenant_id},
    )
    return [dict(r) for r in rows]


async def _user_activity(tenant_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT u.name, u.role, COUNT(d.document_id) AS uploads_today
        FROM users u
        LEFT JOIN documents d ON d.uploaded_by = u.user_id AND d.created_at >= NOW()::date
        WHERE u.tenant_id = :tid
        GROUP BY u.user_id, u.name, u.role
        HAVING COUNT(d.document_id) > 0
        ORDER BY uploads_today DESC LIMIT 10
        """,
        {"tid": tenant_id},
    )
    return [dict(r) for r in rows]


async def _doctor_documents(user_id: str, tenant_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT d.report_type, d.status, d.created_at, f.name AS facility
        FROM documents d
        LEFT JOIN facilities f ON f.facility_id = d.facility_id
        WHERE d.uploaded_by = :uid AND d.tenant_id = :tid
        ORDER BY d.created_at DESC LIMIT 10
        """,
        {"uid": user_id, "tid": tenant_id},
    )
    return [dict(r) for r in rows]


async def _doctor_patients(user_id: str, tenant_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT DISTINCT p.name, p.dob, p.gender, p.status, p.external_id
        FROM patients p
        JOIN documents d ON d.patient_id = p.patient_id
        WHERE d.uploaded_by = :uid AND d.tenant_id = :tid
        ORDER BY p.name LIMIT 20
        """,
        {"uid": user_id, "tid": tenant_id},
    )
    return [dict(r) for r in rows]


async def _doctor_reports(user_id: str, tenant_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT r.report_type, r.report_date, r.extraction_status,
               ROUND(r.extraction_confidence::numeric * 100, 1) AS confidence_pct,
               p.name AS patient_name, f.name AS facility
        FROM reports r
        JOIN documents d  ON d.document_id = r.document_id
        JOIN patients  p  ON p.patient_id  = r.patient_id
        JOIN facilities f ON f.facility_id = r.facility_id
        WHERE d.uploaded_by = :uid AND d.tenant_id = :tid
        ORDER BY r.report_date DESC NULLS LAST, r.created_at DESC LIMIT 10
        """,
        {"uid": user_id, "tid": tenant_id},
    )
    return [dict(r) for r in rows]


async def _doctor_flagged_results(user_id: str, tenant_id: str) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT rr.test_name, rr.value, rr.unit, rr.reference_range, rr.flag,
               p.name AS patient_name, r.report_type, r.report_date
        FROM report_results rr
        JOIN reports   r  ON r.report_id   = rr.report_id
        JOIN documents d  ON d.document_id = r.document_id
        JOIN patients  p  ON p.patient_id  = r.patient_id
        WHERE d.uploaded_by = :uid AND d.tenant_id = :tid
          AND rr.flag IN ('critical', 'high', 'low')
        ORDER BY CASE rr.flag WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                 r.report_date DESC NULLS LAST
        LIMIT 15
        """,
        {"uid": user_id, "tid": tenant_id},
    )
    return [dict(r) for r in rows]


# ── On-demand tool implementations (called by Claude when it needs detail) ────

async def tool_get_failures(tenant_id: str, facility: str | None, limit: int) -> str:
    rows = await db.fetch_all(
        """
        SELECT d.document_id::text, d.report_type, d.error_reason,
               d.retry_count, f.name AS facility,
               d.created_at, d.updated_at
        FROM documents d
        LEFT JOIN facilities f ON f.facility_id = d.facility_id
        WHERE d.tenant_id = :tid
          AND d.status = 'failed'
          AND (:facility = '' OR f.name ILIKE :facility)
        ORDER BY d.updated_at DESC
        LIMIT :lim
        """,
        {"tid": tenant_id, "facility": facility or "", "lim": limit},
    )
    if not rows:
        return "No failures found."
    lines = [
        f"- [{r['facility']}] {r['report_type']} | error: {r['error_reason'] or 'unknown'} "
        f"| retries: {r['retry_count']} | updated: {str(r['updated_at'])[:16]}"
        for r in rows
    ]
    return f"Found {len(rows)} failure(s):\n" + "\n".join(lines)


async def tool_get_stuck_documents(tenant_id: str, limit: int) -> str:
    rows = await db.fetch_all(
        """
        SELECT d.document_id::text, d.report_type, d.status,
               f.name AS facility,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.created_at)) / 60) AS minutes_stuck
        FROM documents d
        LEFT JOIN facilities f ON f.facility_id = d.facility_id
        WHERE d.tenant_id = :tid
          AND d.status IN ('received', 'ocr', 'extracting')
          AND d.created_at < NOW() - INTERVAL '30 minutes'
        ORDER BY d.created_at ASC
        LIMIT :lim
        """,
        {"tid": tenant_id, "lim": limit},
    )
    if not rows:
        return "No stuck documents found."
    lines = [
        f"- [{r['facility']}] {r['report_type']} | stuck in '{r['status']}' for {r['minutes_stuck']} min"
        for r in rows
    ]
    return f"{len(rows)} stuck document(s):\n" + "\n".join(lines)


async def tool_get_documents_by_facility(tenant_id: str, facility: str, limit: int) -> str:
    rows = await db.fetch_all(
        """
        SELECT d.document_id::text, d.report_type, d.status,
               d.created_at, f.name AS facility
        FROM documents d
        JOIN facilities f ON f.facility_id = d.facility_id
        WHERE d.tenant_id = :tid
          AND f.name ILIKE :facility
          AND d.created_at >= NOW()::date
        ORDER BY d.created_at DESC
        LIMIT :lim
        """,
        {"tid": tenant_id, "facility": f"%{facility}%", "lim": limit},
    )
    if not rows:
        return f"No documents found for facility matching '{facility}' today."
    lines = [
        f"- {r['report_type']} | {r['status']} | {str(r['created_at'])[:16]}"
        for r in rows
    ]
    return f"{len(rows)} document(s) for '{facility}' today:\n" + "\n".join(lines)


async def tool_get_user_uploads(tenant_id: str, limit: int) -> str:
    rows = await db.fetch_all(
        """
        SELECT u.name, u.role, u.email,
               COUNT(d.document_id) AS uploads,
               COUNT(*) FILTER (WHERE d.status = 'failed') AS failures
        FROM users u
        LEFT JOIN documents d ON d.uploaded_by = u.user_id AND d.created_at >= NOW()::date
        WHERE u.tenant_id = :tid
        GROUP BY u.user_id, u.name, u.role, u.email
        ORDER BY uploads DESC
        LIMIT :lim
        """,
        {"tid": tenant_id, "lim": limit},
    )
    if not rows:
        return "No upload activity found."
    lines = [
        f"- {r['name']} ({r['role']}): {r['uploads']} uploads, {r['failures']} failed"
        for r in rows
    ]
    return "\n".join(lines)


# Map tool name → function
ADMIN_TOOLS = {
    "get_failures": tool_get_failures,
    "get_stuck_documents": tool_get_stuck_documents,
    "get_documents_by_facility": tool_get_documents_by_facility,
    "get_user_uploads": tool_get_user_uploads,
}

# Tool schemas sent to Claude
ADMIN_TOOL_SCHEMAS = [
    {
        "name": "get_failures",
        "description": "Get detailed list of failed documents. Use when the user asks for failure details, DLQ contents, or specific error reasons.",
        "input_schema": {
            "type": "object",
            "properties": {
                "facility": {"type": "string", "description": "Filter by facility name. Leave empty for all facilities."},
                "limit":    {"type": "integer", "description": "Max rows to return. Default 20, max 50.", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_stuck_documents",
        "description": "Get documents stuck in the pipeline for more than 30 minutes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max rows to return.", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_documents_by_facility",
        "description": "Get today's documents for a specific facility.",
        "input_schema": {
            "type": "object",
            "properties": {
                "facility": {"type": "string", "description": "Facility name or partial name to search."},
                "limit":    {"type": "integer", "default": 20},
            },
            "required": ["facility"],
        },
    },
    {
        "name": "get_user_uploads",
        "description": "Get upload counts and failure counts per user for today.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
]


# ── Prompt builder ────────────────────────────────────────────────────────────

async def build_system_prompt(role: str, tenant_id: str, user_id: str) -> str:
    stats = await _base_stats(tenant_id)

    base = (
        "You are a healthcare data platform assistant for HealthAI.\n"
        "Answer only from the data provided or fetched via tools. Do not guess or hallucinate numbers.\n\n"
        "=== TODAY'S PIPELINE STATS ===\n"
        f"- Documents processed today: {stats['docs_today']}\n"
        f"- Successful extractions today: {stats['success_rate'] or 0}%\n"
        f"- Failed today: {stats['failed_today']}\n"
        f"- Total DLQ backlog: {stats['dlq_count']}\n"
        f"- Documents stuck >30 min: {stats['stuck_count']}\n"
        f"- Active uploaders today: {stats['active_users']}\n"
    )

    if role in ("tenant_admin", "manager", "ops"):
        facilities, user_activity = await asyncio.gather(
            _facility_breakdown(tenant_id),
            _user_activity(tenant_id),
        )
        fac_lines = "\n".join(
            f"  - {f['facility']}: {f['total']} docs, {f['failed']} failed"
            for f in facilities
        ) or "  No facility data today."
        user_lines = "\n".join(
            f"  - {u['name']} ({u['role']}): {u['uploads_today']} uploads"
            for u in user_activity
        ) or "  No uploads today."
        role_context = (
            f"\n=== FACILITY BREAKDOWN (today) ===\n{fac_lines}\n"
            f"\n=== USER UPLOAD ACTIVITY (today) ===\n{user_lines}\n"
            "\nFor detailed failure lists, stuck documents, or per-facility drill-downs, "
            "use the available tools to fetch the data.\n"
        )
        restrictions = (
            "\n=== WHAT YOU MUST NOT DO ===\n"
            "- Do not reveal individual patient names, DOB, diagnoses, or test results.\n"
            "- Do not compare or reveal data from other tenants.\n"
            "- Do not make clinical recommendations.\n"
            "- For patient-level detail, direct the user to the Patients page.\n"
        )

    elif role == "doctor":
        my_docs, my_patients, my_reports, flagged = await asyncio.gather(
            _doctor_documents(user_id, tenant_id),
            _doctor_patients(user_id, tenant_id),
            _doctor_reports(user_id, tenant_id),
            _doctor_flagged_results(user_id, tenant_id),
        )
        doc_lines = "\n".join(
            f"  - {d['report_type']} | {d['status']} | {d['facility']} | {str(d['created_at'])[:16]}"
            for d in my_docs
        ) or "  No documents uploaded by you yet."
        patient_lines = "\n".join(
            f"  - {p['name']} | DOB: {p['dob']} | {p['gender']} | Status: {p['status']} | ID: {p['external_id']}"
            for p in my_patients
        ) or "  No patients linked to your documents yet."
        report_lines = "\n".join(
            f"  - {r['patient_name']} | {r['report_type']} | {r['report_date']} | "
            f"{r['extraction_status']} ({r['confidence_pct']}% confidence) | {r['facility']}"
            for r in my_reports
        ) or "  No extracted reports yet."
        flagged_lines = "\n".join(
            f"  - [{r['flag'].upper()}] {r['patient_name']} — {r['test_name']}: "
            f"{r['value']} {r['unit']} (ref: {r['reference_range']}) | {r['report_type']} {r['report_date']}"
            for r in flagged
        ) or "  No abnormal results found."
        role_context = (
            f"\n=== YOUR RECENT UPLOADS ===\n{doc_lines}\n"
            f"\n=== YOUR PATIENTS ===\n{patient_lines}\n"
            f"\n=== RECENT EXTRACTED REPORTS ===\n{report_lines}\n"
            f"\n=== ABNORMAL / CRITICAL RESULTS ===\n{flagged_lines}\n"
        )
        restrictions = (
            "\n=== WHAT YOU MUST NOT DO ===\n"
            "- Only discuss patients, reports, and results belonging to this doctor.\n"
            "- Do not reveal data belonging to other doctors or users.\n"
            "- Do not make clinical diagnoses or prescribe treatments.\n"
            "- Do not reveal data from other tenants.\n"
        )

    elif role in ("analyst", "viewer"):
        role_context = ""
        restrictions = (
            "\n=== WHAT YOU MUST NOT DO ===\n"
            "- Do not reveal any individual patient names, IDs, DOB, diagnoses, or test results.\n"
            "- Do not reveal which specific users uploaded documents.\n"
            "- Only answer with aggregate counts and rates — no row-level detail.\n"
            "- If asked about specific patients or users, refuse and redirect to the appropriate page.\n"
            "- Do not make clinical recommendations.\n"
        )
    else:
        role_context = ""
        restrictions = (
            "\n=== WHAT YOU MUST NOT DO ===\n"
            "- Do not reveal patient names, IDs, or health records.\n"
            "- Do not make clinical recommendations.\n"
        )

    return base + role_context + restrictions + "\nKeep responses concise. Use bullet points for lists."


# ── Endpoint with tool-call loop ──────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
) -> ChatResponse:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    role      = current_user.get("role", "viewer")
    tenant_id = current_user["tenant_id"]
    user_id   = current_user["user_id"]

    system  = await build_system_prompt(role, tenant_id, user_id)
    messages = [m.model_dump() for m in body.messages]

    # Only admin roles get tools — doctors and analysts work from injected context only
    tools = ADMIN_TOOL_SCHEMAS if role in ("tenant_admin", "manager", "ops") else []

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # Tool-call loop: keep going until Claude stops calling tools
        for _ in range(5):  # max 5 tool rounds to prevent runaway loops
            payload: dict = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1500,
                "system": system,
                "messages": messages,
            }
            if tools:
                payload["tools"] = tools

            resp = await client.post(ANTHROPIC_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(502, detail=f"Anthropic API error: {resp.text}")

            data        = resp.json()
            stop_reason = data.get("stop_reason")
            content     = data.get("content", [])

            if stop_reason != "tool_use":
                # Claude is done — extract text reply
                for block in content:
                    if block.get("type") == "text":
                        return ChatResponse(reply=block["text"])
                return ChatResponse(reply="No response generated.")

            # Claude wants to call tools — run them and feed results back
            messages.append({"role": "assistant", "content": content})

            tool_results = []
            for block in content:
                if block.get("type") != "tool_use":
                    continue
                tool_name   = block["name"]
                tool_input  = block.get("input", {})
                tool_use_id = block["id"]

                fn = ADMIN_TOOLS.get(tool_name)
                if fn:
                    result_text = await fn(
                        tenant_id=tenant_id,
                        **{k: v for k, v in tool_input.items()},
                    )
                else:
                    result_text = f"Unknown tool: {tool_name}"

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tool_use_id,
                    "content":     result_text,
                })

            messages.append({"role": "user", "content": tool_results})

    return ChatResponse(reply="Could not complete the request. Please try again.")
