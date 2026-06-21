from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class AuditLog(BaseModel):
    id: int
    user: str
    action: str
    resource: str
    ip: str
    time: str
    tenant: str


_LOGS: list[AuditLog] = [
    AuditLog(id=1, user="Dr. Mehta",       action="Viewed patient report",   resource="PT-2041 CBC",      ip="10.0.1.42",  time="11:58 AM", tenant="City General"),
    AuditLog(id=2, user="admin@healthai",  action="Exported dataset",        resource="June analytics",   ip="10.0.0.1",   time="11:30 AM", tenant="System"),
    AuditLog(id=3, user="analyst@apollo",  action="Filtered patient cohort", resource="HbA1c > 7.5",     ip="10.0.2.11",  time="11:12 AM", tenant="Apollo Diagnostics"),
    AuditLog(id=4, user="Dr. Singh",       action="Viewed patient report",   resource="PT-2313 ECG",      ip="10.0.3.88",  time="10:45 AM", tenant="City General"),
    AuditLog(id=5, user="ops@sunrise",     action="Triggered manual retry",  resource="DLQ batch #44",   ip="10.0.4.22",  time="09:32 AM", tenant="Sunrise Clinic"),
    AuditLog(id=6, user="admin@healthai",  action="Created new user",        resource="dr.rao@riverside", ip="10.0.0.1",   time="09:10 AM", tenant="System"),
]


@router.get("/", response_model=list[AuditLog])
def list_audit_logs(search: Optional[str] = Query(None)) -> list[AuditLog]:
    if not search:
        return _LOGS
    q = search.lower()
    return [
        log for log in _LOGS
        if q in log.user.lower() or q in log.action.lower() or q in log.tenant.lower()
    ]
