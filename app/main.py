from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before local imports so env vars are set when modules load

from fastapi import FastAPI

from app.api.routers import ai, admin, audit, auth, dashboard, patients, queue, tenants, upload
from app.db import snowflake_client
from app.db.session import db
from app.db.warehouse import warehouse
from app.events.kafka import shutdown_producer


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await warehouse.connect()
    try:
        yield
    finally:
        await db.disconnect()
        await warehouse.disconnect()
        await shutdown_producer()
        snowflake_client.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Healthcare AI Platform Backend",
        version="0.1.0",
        description="FastAPI backend for the healthcare AI platform.",
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    def health_check() -> dict:
        return {"status": "ok"}

    app.include_router(auth.router,     prefix="/api/v1/auth",      tags=["auth"])
    app.include_router(admin.router,    prefix="/api/v1/admin",     tags=["admin"])
    app.include_router(patients.router, prefix="/api/v1/patients",  tags=["patients"])
    app.include_router(upload.router,   prefix="/api/v1/upload",    tags=["upload"])
    app.include_router(dashboard.router,prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(queue.router,    prefix="/api/v1/queue",     tags=["queue"])
    app.include_router(tenants.router,  prefix="/api/v1/tenants",   tags=["tenants"])
    app.include_router(audit.router,    prefix="/api/v1/audit",     tags=["audit"])
    app.include_router(ai.router,       prefix="/api/v1/ai",        tags=["ai"])

    return app
