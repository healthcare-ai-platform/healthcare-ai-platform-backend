from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.session import db

router = APIRouter()


class KPIs(BaseModel):
    documentsToday: int
    documentsDelta: str
    avgTurnaround: str
    turnaroundDelta: str
    extractionSuccess: str
    successDelta: str
    dlqBacklog: int
    dlqDelta: str


class PipelineStage(BaseModel):
    name: str
    count: int
    color: str
    pct: int


class Alert(BaseModel):
    id: str
    type: str
    title: str
    detail: str
    time: str


class ThroughputPoint(BaseModel):
    hour: str
    docs: int


@router.get("/kpis", response_model=KPIs)
async def get_kpis(current_user: dict = Depends(get_current_user)) -> KPIs:
    tenant_id = current_user["tenant_id"]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    row = await db.fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE created_at >= :today)                       AS docs_today,
            COUNT(*) FILTER (WHERE created_at >= :today AND status = 'failed') AS failed_today,
            COUNT(*) FILTER (WHERE created_at < :today AND created_at >= :yesterday) AS docs_yesterday,
            AVG(
                EXTRACT(EPOCH FROM (updated_at - created_at)) / 60.0
            ) FILTER (WHERE status = 'loaded' AND created_at >= :today)        AS avg_min,
            COUNT(*) FILTER (WHERE status = 'failed')                           AS dlq_backlog,
            COUNT(*) FILTER (WHERE status = 'failed' AND created_at >= :today) AS dlq_today
        FROM documents
        WHERE tenant_id = :tenant_id
        """,
        {
            "tenant_id": tenant_id,
            "today": today_start,
            "yesterday": today_start.replace(day=today_start.day - 1),
        },
    )

    docs_today     = row["docs_today"] or 0
    docs_yesterday = row["docs_yesterday"] or 0
    failed_today   = row["failed_today"] or 0
    dlq_backlog    = row["dlq_backlog"] or 0
    dlq_today      = row["dlq_today"] or 0
    avg_min        = float(row["avg_min"] or 0.0)

    success_rate = (
        round((1 - failed_today / docs_today) * 100, 1) if docs_today > 0 else 100.0
    )

    if docs_yesterday > 0:
        delta_pct = round((docs_today - docs_yesterday) / docs_yesterday * 100)
        docs_delta = f"+{delta_pct}%" if delta_pct >= 0 else f"{delta_pct}%"
    else:
        docs_delta = "—"

    avg_str = f"{avg_min:.1f} min" if avg_min > 0 else "—"

    return KPIs(
        documentsToday=docs_today,
        documentsDelta=docs_delta,
        avgTurnaround=avg_str,
        turnaroundDelta="",
        extractionSuccess=f"{success_rate}%",
        successDelta="",
        dlqBacklog=dlq_backlog,
        dlqDelta=f"+{dlq_today} today" if dlq_today > 0 else "0 today",
    )


@router.get("/pipeline-stages", response_model=list[PipelineStage])
async def get_pipeline_stages(current_user: dict = Depends(get_current_user)) -> list[PipelineStage]:
    tenant_id = current_user["tenant_id"]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = await db.fetch_all(
        """
        SELECT status, COUNT(*) AS cnt
        FROM documents
        WHERE tenant_id = :tenant_id AND created_at >= :today
        GROUP BY status
        """,
        {"tenant_id": tenant_id, "today": today_start},
    )

    counts = {r["status"]: r["cnt"] for r in rows}
    total = sum(counts.values()) or 1

    STAGE_MAP = [
        ("received",   "Received",          "#185fa5"),
        ("ocr",        "OCR complete",       "#0f6e56"),
        ("extracting", "LLM extracting",     "#534ab7"),
        ("loaded",     "Loaded",             "#3b6d11"),
        ("failed",     "Failed / DLQ",       "#a32d2d"),
    ]

    return [
        PipelineStage(
            name=label,
            count=counts.get(status, 0),
            color=color,
            pct=round(counts.get(status, 0) / total * 100),
        )
        for status, label, color in STAGE_MAP
    ]


@router.get("/alerts", response_model=list[Alert])
async def get_alerts(current_user: dict = Depends(get_current_user)) -> list[Alert]:
    tenant_id = current_user["tenant_id"]

    rows = await db.fetch_all(
        """
        SELECT
            d.document_id::text AS id,
            d.status,
            d.error_reason,
            d.report_type,
            d.created_at,
            d.updated_at,
            f.name AS facility_name
        FROM documents d
        LEFT JOIN facilities f ON f.facility_id = d.facility_id
        WHERE d.tenant_id = :tenant_id
          AND (
            d.status = 'failed'
            OR (d.status IN ('received','ocr','extracting')
                AND d.created_at < NOW() - INTERVAL '30 minutes')
          )
        ORDER BY d.updated_at DESC
        LIMIT 10
        """,
        {"tenant_id": tenant_id},
    )

    alerts = []
    for row in rows:
        if row["status"] == "failed":
            alert_type = "error"
            title = f"Extraction failed — {row['facility_name'] or 'Unknown'}"
            detail = row["error_reason"] or f"{row['report_type']} document failed"
        else:
            alert_type = "warning"
            title = f"Stuck in pipeline — {row['facility_name'] or 'Unknown'}"
            detail = f"{row['report_type']} stuck in '{row['status']}' for >30 min"

        alerts.append(Alert(
            id=row["id"],
            type=alert_type,
            title=title,
            detail=detail,
            time=row["updated_at"].strftime("%-I:%M %p") if row["updated_at"] else "",
        ))

    return alerts


@router.get("/throughput", response_model=list[ThroughputPoint])
async def get_throughput(current_user: dict = Depends(get_current_user)) -> list[ThroughputPoint]:
    tenant_id = current_user["tenant_id"]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = await db.fetch_all(
        """
        SELECT
            EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC') AS hr,
            COUNT(*) AS cnt
        FROM documents
        WHERE tenant_id = :tenant_id AND created_at >= :today
        GROUP BY hr
        ORDER BY hr
        """,
        {"tenant_id": tenant_id, "today": today_start},
    )

    counts = {int(r["hr"]): r["cnt"] for r in rows}

    def fmt_hour(h: int) -> str:
        if h == 0:   return "12am"
        if h < 12:   return f"{h}am"
        if h == 12:  return "12pm"
        return f"{h - 12}pm"

    return [
        ThroughputPoint(hour=fmt_hour(h), docs=counts.get(h, 0))
        for h in range(0, 24, 2)
    ]
