from fastapi import APIRouter
from pydantic import BaseModel

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
    id: int
    type: str
    title: str
    detail: str
    time: str


class ThroughputPoint(BaseModel):
    hour: str
    docs: int


@router.get("/kpis", response_model=KPIs)
def get_kpis() -> KPIs:
    return KPIs(
        documentsToday=1284,
        documentsDelta="+12%",
        avgTurnaround="4.2 min",
        turnaroundDelta="-0.8 min",
        extractionSuccess="97.3%",
        successDelta="-0.4% vs target",
        dlqBacklog=18,
        dlqDelta="+6 since 9am",
    )


@router.get("/pipeline-stages", response_model=list[PipelineStage])
def get_pipeline_stages() -> list[PipelineStage]:
    return [
        PipelineStage(name="Received",           count=312, color="#185fa5", pct=100),
        PipelineStage(name="OCR complete",        count=289, color="#0f6e56", pct=93),
        PipelineStage(name="LLM extracted",       count=271, color="#534ab7", pct=87),
        PipelineStage(name="Validated",           count=264, color="#3b6d11", pct=85),
        PipelineStage(name="Loaded to Redshift",  count=258, color="#185fa5", pct=83),
        PipelineStage(name="Failed / DLQ",        count=18,  color="#a32d2d", pct=6),
    ]


@router.get("/alerts", response_model=list[Alert])
def get_alerts() -> list[Alert]:
    return [
        Alert(id=1, type="error",   title="DLQ spike — City General Hospital",    detail="6 documents failed LLM extraction",            time="11:42 AM"),
        Alert(id=2, type="warning", title="SLA breach risk — Apollo Diagnostics", detail="Turnaround at 7.1 min, threshold 8 min",        time="10:58 AM"),
        Alert(id=3, type="success", title="Backlog cleared — Sunrise Clinic",     detail="Queue returned to 0 after retry run",           time="09:31 AM"),
        Alert(id=4, type="warning", title="Schema validation errors — Lab batch", detail="Missing units field in 12 CBC reports",         time="08:14 AM"),
        Alert(id=5, type="error",   title="OCR timeout — Metro Health Labs",      detail="3 high-res scans exceeded 60s limit",          time="07:50 AM"),
    ]


@router.get("/throughput", response_model=list[ThroughputPoint])
def get_throughput() -> list[ThroughputPoint]:
    return [
        ThroughputPoint(hour="12am", docs=12),
        ThroughputPoint(hour="2am",  docs=8),
        ThroughputPoint(hour="4am",  docs=5),
        ThroughputPoint(hour="6am",  docs=42),
        ThroughputPoint(hour="8am",  docs=198),
        ThroughputPoint(hour="10am", docs=287),
        ThroughputPoint(hour="12pm", docs=312),
        ThroughputPoint(hour="2pm",  docs=198),
        ThroughputPoint(hour="4pm",  docs=145),
        ThroughputPoint(hour="6pm",  docs=77),
    ]
