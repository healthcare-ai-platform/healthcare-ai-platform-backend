from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class Patient(BaseModel):
    id: int
    name: str
    age: int
    conditions: List[str]


@router.get("/", response_model=List[Patient])
def list_patients() -> List[Patient]:
    return [
        Patient(id=1, name="John Doe", age=45, conditions=["hypertension"]),
        Patient(id=2, name="Maria Smith", age=38, conditions=["diabetes"]),
    ]
