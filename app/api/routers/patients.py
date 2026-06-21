from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

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


_PATIENTS: list[Patient] = [
    Patient(id="PT-2041", name="Ravi Sharma",   age=54, doctor="Dr. Mehta",  hospital="City General",      lastReport="CBC Report",        date="Jun 20", status="normal",   reports=8),
    Patient(id="PT-1892", name="Sunita Verma",  age=38, doctor="Dr. Patel",  hospital="Apollo Diagnostics", lastReport="Discharge Summary", date="Jun 20", status="review",   reports=12),
    Patient(id="PT-2209", name="Arjun Nair",    age=62, doctor="Dr. Singh",  hospital="Sunrise Clinic",    lastReport="Prescription",      date="Jun 19", status="normal",   reports=4),
    Patient(id="PT-1773", name="Priya Iyer",    age=45, doctor="Dr. Kumar",  hospital="Metro Health",      lastReport="Referral Note",     date="Jun 19", status="abnormal", reports=6),
    Patient(id="PT-2310", name="Deepak Joshi",  age=71, doctor="Dr. Mehta",  hospital="City General",      lastReport="Lipid Panel",       date="Jun 18", status="abnormal", reports=15),
    Patient(id="PT-2311", name="Kavya Reddy",   age=29, doctor="Dr. Rao",    hospital="Riverside Care",    lastReport="MRI Report",        date="Jun 18", status="normal",   reports=2),
    Patient(id="PT-2312", name="Manish Gupta",  age=48, doctor="Dr. Patel",  hospital="Apollo Diagnostics", lastReport="HbA1c Result",     date="Jun 17", status="review",   reports=9),
    Patient(id="PT-2313", name="Anita Desai",   age=66, doctor="Dr. Singh",  hospital="City General",      lastReport="ECG Report",        date="Jun 17", status="abnormal", reports=11),
]


@router.get("/", response_model=list[Patient])
def list_patients(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> list[Patient]:
    results = _PATIENTS
    if search:
        q = search.lower()
        results = [p for p in results if q in p.name.lower() or q in p.id.lower() or q in p.hospital.lower()]
    if status and status != "all":
        results = [p for p in results if p.status == status]
    return results
