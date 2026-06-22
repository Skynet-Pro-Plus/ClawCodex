"""FastAPI control plane for ClawCodex."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes import attachments, intelligence, models, projects, repos, rules, safety, settings, tasks, tools
from ..auth import get_api_key


INDEX_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

LOCAL_ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
}


def create_app() -> FastAPI:
    app = FastAPI(title="ClawCodex API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(LOCAL_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
    app.include_router(safety.router, prefix="/api/safety", tags=["safety"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(models.router, prefix="/api/models", tags=["models"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
    app.include_router(attachments.router, prefix="/api/attachments", tags=["attachments"])
    app.include_router(rules.router, prefix="/api/rules", tags=["rules"])
    app.include_router(intelligence.router, prefix="/api/intelligence", tags=["intelligence"])

    # ----- New headless API routes -----
    from fastapi import APIRouter

    missions_router = APIRouter()

    @missions_router.post("/missions", tags=["missions"])
    async def create_mission(payload: dict, api_key: str = Depends(get_api_key)):
        # Placeholder implementation – in a full system this would create a Mission object.
        return {"mission_id": "demo-mission", "status": "created", "payload": payload}

    @missions_router.get("/missions/{mission_id}", tags=["missions"])
    async def get_mission(mission_id: str, api_key: str = Depends(get_api_key)):
        # Placeholder – return dummy mission data.
        return {"mission_id": mission_id, "status": "running"}

    @missions_router.post("/missions/{mission_id}/approve-plan", tags=["missions"])
    async def approve_plan(mission_id: str, api_key: str = Depends(get_api_key)):
        return {"mission_id": mission_id, "plan": "approved"}

    @missions_router.post("/missions/{mission_id}/run", tags=["missions"])
    async def run_mission(mission_id: str, api_key: str = Depends(get_api_key)):
        return {"mission_id": mission_id, "run": "started"}

    app.include_router(missions_router, prefix="/api/v1")

    @app.middleware("http")
    async def enforce_local_api(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in LOCAL_ORIGINS:
            return JSONResponse(status_code=403, content={"ok": False, "error": {"code": "FORBIDDEN_ORIGIN", "message": "Origin is not allowed", "details": {}}})
        token = os.environ.get("CLAWCODEX_API_TOKEN")
        if token and request.url.path.startswith("/api/") and request.headers.get("x-clawcodex-token") != token:
            return JSONResponse(status_code=401, content={"ok": False, "error": {"code": "AUTH_REQUIRED", "message": "Missing or invalid API token", "details": {}}})
        return await call_next(request)

    # UI assets have been removed for headless operation.
    # The frontend directory is no longer used.

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "name": "ClawCodex API", "status": "healthy"}

    @app.get("/", response_model=None)
    def root():
        # Simple health endpoint for headless mode.
        return {
            "ok": True,
            "name": "ClawCodex API",
            "docs": "/docs",
            "health": "/health",
            "message": "Headless API server – UI has been removed.",
        }

    @app.get("/{spa_path:path}", response_model=None)
    def spa_fallback(spa_path: str):
        # No SPA fallback needed in headless mode.
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    @app.exception_handler(Exception)
    async def handle_exception(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": {"code": exc.__class__.__name__, "message": str(exc), "details": {}}},
        )

    return app


app = create_app()
