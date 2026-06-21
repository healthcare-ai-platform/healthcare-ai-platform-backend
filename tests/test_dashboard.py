"""
GET /api/v1/dashboard/* — static/hardcoded data, no auth, no DB.
All these tests use unit_client (DB connections are mocked).
"""


async def test_kpis_shape(unit_client):
    r = await unit_client.get("/api/v1/dashboard/kpis")
    assert r.status_code == 200
    data = r.json()
    assert "documentsToday" in data
    assert "avgTurnaround" in data
    assert "extractionSuccess" in data
    assert "dlqBacklog" in data
    assert isinstance(data["documentsToday"], int)
    assert isinstance(data["dlqBacklog"], int)


async def test_kpis_values(unit_client):
    r = await unit_client.get("/api/v1/dashboard/kpis")
    data = r.json()
    assert data["documentsToday"] == 1284
    assert data["avgTurnaround"] == "4.2 min"
    assert data["extractionSuccess"] == "97.3%"
    assert data["dlqBacklog"] == 18


async def test_pipeline_stages_shape(unit_client):
    r = await unit_client.get("/api/v1/dashboard/pipeline-stages")
    assert r.status_code == 200
    stages = r.json()
    assert isinstance(stages, list)
    assert len(stages) == 6
    for s in stages:
        assert "name" in s
        assert "count" in s
        assert "color" in s
        assert "pct" in s


async def test_pipeline_stages_values(unit_client):
    r = await unit_client.get("/api/v1/dashboard/pipeline-stages")
    stages = r.json()
    names = [s["name"] for s in stages]
    assert "Received" in names
    assert "Failed / DLQ" in names
    dlq = next(s for s in stages if s["name"] == "Failed / DLQ")
    assert dlq["count"] == 18
    assert dlq["color"] == "#a32d2d"


async def test_alerts_shape(unit_client):
    r = await unit_client.get("/api/v1/dashboard/alerts")
    assert r.status_code == 200
    alerts = r.json()
    assert isinstance(alerts, list)
    assert len(alerts) == 5
    for a in alerts:
        assert "id" in a
        assert "type" in a
        assert "title" in a
        assert "detail" in a
        assert "time" in a


async def test_alerts_types(unit_client):
    r = await unit_client.get("/api/v1/dashboard/alerts")
    types = {a["type"] for a in r.json()}
    assert types == {"error", "warning", "success"}


async def test_throughput_shape(unit_client):
    r = await unit_client.get("/api/v1/dashboard/throughput")
    assert r.status_code == 200
    points = r.json()
    assert isinstance(points, list)
    assert len(points) == 10
    for p in points:
        assert "hour" in p
        assert "docs" in p
        assert isinstance(p["docs"], int)


async def test_throughput_peak_at_noon(unit_client):
    r = await unit_client.get("/api/v1/dashboard/throughput")
    points = {p["hour"]: p["docs"] for p in r.json()}
    assert points["12pm"] == 312
