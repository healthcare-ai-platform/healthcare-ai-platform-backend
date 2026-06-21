from fastapi import FastAPI

from app.api.routers import ai, audit, dashboard, patients, queue, tenants, upload


def create_app() -> FastAPI:
    app = FastAPI(
        title="Healthcare AI Platform Backend",
        version="0.1.0",
        description="FastAPI backend for the healthcare AI platform.",
    )

    @app.get("/health", tags=["health"])
    def health_check() -> dict:
        return {"status": "ok"}

    app.include_router(patients.router,  prefix="/api/v1/patients",  tags=["patients"])
    app.include_router(upload.router,    prefix="/api/v1/upload",    tags=["upload"])
    app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(queue.router,     prefix="/api/v1/queue",     tags=["queue"])
    app.include_router(tenants.router,   prefix="/api/v1/tenants",   tags=["tenants"])
    app.include_router(audit.router,     prefix="/api/v1/audit",     tags=["audit"])
    app.include_router(ai.router,        prefix="/api/v1/ai",        tags=["ai"])

    return app
