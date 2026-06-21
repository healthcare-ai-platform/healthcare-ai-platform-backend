from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class QueueDocument(BaseModel):
    id: str
    name: str
    type: str
    status: str
    tenant: str


_QUEUE: list[QueueDocument] = [
    QueueDocument(id="PT-2041", name="CBC Report",         type="Lab",        status="loaded",     tenant="City General"),
    QueueDocument(id="PT-1892", name="Discharge Summary",  type="Clinical",   status="extracting", tenant="Apollo Diagnostics"),
    QueueDocument(id="PT-2209", name="Prescription",       type="Rx",         status="ocr",        tenant="Sunrise Clinic"),
    QueueDocument(id="PT-1773", name="Referral Note",      type="Clinical",   status="failed",     tenant="Metro Health"),
    QueueDocument(id="PT-2310", name="Lipid Panel",        type="Lab",        status="queued",     tenant="City General"),
    QueueDocument(id="PT-2311", name="MRI Report",         type="Imaging",    status="queued",     tenant="Riverside Care"),
    QueueDocument(id="PT-2312", name="HbA1c Result",       type="Lab",        status="loaded",     tenant="Apollo Diagnostics"),
    QueueDocument(id="PT-2313", name="ECG Report",         type="Cardiology", status="extracting", tenant="City General"),
    QueueDocument(id="PT-2314", name="Thyroid Panel",      type="Lab",        status="failed",     tenant="Metro Health"),
    QueueDocument(id="PT-2315", name="Chest X-Ray Note",  type="Imaging",    status="queued",     tenant="Sunrise Clinic"),
]


@router.get("/", response_model=list[QueueDocument])
def list_queue(status: Optional[str] = Query(None)) -> list[QueueDocument]:
    if status:
        return [d for d in _QUEUE if d.status == status]
    return _QUEUE
