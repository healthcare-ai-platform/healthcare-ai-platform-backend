from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.schemas import Page
from app.db.session import db

router = APIRouter()


class Patient(BaseModel):
    id: str
    name: str
    age: int
    doctor: str
    hospital: str
    lastReport: str
    date: str
    status: str
    reports: int


@router.get("/", response_model=Page[Patient])
async def list_patients(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Page[Patient]:
    tenant_id = current_user["tenant_id"]
    if status == "all":
        status = None

    rows = await db.fetch_all(
        """
        WITH clinical AS (
            SELECT
                p.patient_id,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM report_results rr
                        JOIN reports r2 ON r2.report_id = rr.report_id
                        WHERE r2.patient_id = p.patient_id
                          AND rr.flag IN ('high', 'low', 'critical')
                    ) THEN 'abnormal'
                    WHEN EXISTS (
                        SELECT 1 FROM report_results rr
                        JOIN reports r2 ON r2.report_id = rr.report_id
                        WHERE r2.patient_id = p.patient_id
                          AND rr.flag = 'borderline'
                    ) THEN 'review'
                    ELSE 'normal'
                END AS clinical_status
            FROM patients p
            WHERE p.tenant_id = :tenant_id
        ),
        report_counts AS (
            SELECT patient_id, COUNT(*)::int AS report_count
            FROM reports
            GROUP BY patient_id
        ),
        latest_report AS (
            SELECT DISTINCT ON (r.patient_id)
                r.patient_id,
                r.doctor,
                r.report_type,
                r.report_date,
                r.facility_id
            FROM reports r
            WHERE r.patient_id IN (SELECT patient_id FROM clinical)
            ORDER BY r.patient_id, r.report_date DESC NULLS LAST, r.created_at DESC
        )
        SELECT
            p.patient_id::text                               AS id,
            p.name,
            EXTRACT(YEAR FROM AGE(p.dob))::int               AS age,
            COALESCE(lr.doctor, '')                          AS doctor,
            COALESCE(f.name, '')                             AS hospital,
            COALESCE(lr.report_type, '')                     AS last_report,
            COALESCE(TO_CHAR(lr.report_date, 'Mon DD'), '')  AS date,
            c.clinical_status                                AS status,
            COALESCE(rc.report_count, 0)                     AS reports,
            COUNT(*) OVER ()                                 AS total_count
        FROM patients p
        JOIN clinical c ON c.patient_id = p.patient_id
        LEFT JOIN latest_report lr ON lr.patient_id = p.patient_id
        LEFT JOIN facilities f ON f.facility_id = lr.facility_id
        LEFT JOIN report_counts rc ON rc.patient_id = p.patient_id
        WHERE (:search IS NULL OR
               p.name ILIKE '%' || :search || '%' OR
               p.external_id ILIKE '%' || :search || '%' OR
               f.name ILIKE '%' || :search || '%')
          AND (:status IS NULL OR c.clinical_status = :status)
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
        """,
        {
            "tenant_id": tenant_id,
            "search": search,
            "status": status,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    )

    total = rows[0]["total_count"] if rows else 0
    items = [
        Patient(
            id=row["id"],
            name=row["name"],
            age=row["age"],
            doctor=row["doctor"],
            hospital=row["hospital"],
            lastReport=row["last_report"],
            date=row["date"],
            status=row["status"],
            reports=row["reports"],
        )
        for row in rows
    ]
    return Page.build(items, total, page, page_size)
