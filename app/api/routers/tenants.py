from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.schemas import Page
from app.db.session import db

router = APIRouter()

_COLORS = [
    {"color": "#185fa5", "bg": "#e6f1fb"},
    {"color": "#854f0b", "bg": "#faeeda"},
    {"color": "#534ab7", "bg": "#eeedfe"},
    {"color": "#993556", "bg": "#fbeaf0"},
    {"color": "#0f6e56", "bg": "#e6f5f1"},
]


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


@router.get("/", response_model=Page[Tenant])
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
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
            "limit": page_size,
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
