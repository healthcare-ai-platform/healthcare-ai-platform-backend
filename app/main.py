from fastapi import FastAPI

from app.api.routers import patients, upload


def create_app() -> FastAPI:
    app = FastAPI(
        title="Healthcare AI Platform Backend",
        version="0.1.0",
        description="FastAPI backend for the healthcare AI platform.",
    )

    @app.get("/health", tags=["health"])
    def health_check() -> dict:
        return {"status": "ok"}

    app.include_router(patients.router, prefix="/api/v1/patients", tags=["patients"])
    app.include_router(upload.router, prefix="/api/v1/upload", tags=["upload"])

    return app
