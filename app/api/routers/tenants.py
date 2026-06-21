from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


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


@router.get("/", response_model=list[Tenant])
def list_tenants() -> list[Tenant]:
    return [
        Tenant(id="t1", initials="CG", name="City General Hospital", docs=412, sla="ok",   color="#185fa5", bg="#e6f1fb", failures=6, avgTime="3.8 min"),
        Tenant(id="t2", initials="AD", name="Apollo Diagnostics",    docs=298, sla="risk", color="#854f0b", bg="#faeeda", failures=1, avgTime="7.1 min"),
        Tenant(id="t3", initials="SC", name="Sunrise Clinic",        docs=241, sla="ok",   color="#534ab7", bg="#eeedfe", failures=0, avgTime="3.2 min"),
        Tenant(id="t4", initials="MH", name="Metro Health Labs",     docs=187, sla="ok",   color="#993556", bg="#fbeaf0", failures=4, avgTime="4.5 min"),
        Tenant(id="t5", initials="RC", name="Riverside Care",        docs=146, sla="ok",   color="#854f0b", bg="#faeeda", failures=0, avgTime="4.1 min"),
    ]
