from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(
        title="HACOM AI Telco Engine",
        summary="Deterministic RAN KPI diagnostics with an agent layer on top",
        description=(
            "Proof of concept for applied AI in telco operations. The diagnostic core is "
            "deterministic and runs without any model provider; the agent and retrieval "
            "layers consume it as tools rather than replacing it."
        ),
        version=settings.version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.name, "version": settings.version}

    return app


app = create_app()
