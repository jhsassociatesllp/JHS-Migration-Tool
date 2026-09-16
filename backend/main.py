from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from database import init_db
from api import projects, files, mappings, validation, results, export

app = FastAPI(
    title="Migration Validation & Mapping Tool",
    description="Configuration-driven CSV migration validation, reconciliation, and reporting API.",
    version="1.0.0",
)

allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak stack traces / internal detail to the client.
    return JSONResponse(
        status_code=500,
        content={"detail": {"message": "Something went wrong while processing your request. Please try again."}},
    )


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(projects.router)
app.include_router(files.router)
app.include_router(mappings.router)
app.include_router(mappings.templates_router)
app.include_router(validation.router)
app.include_router(results.router)
app.include_router(export.router)


# In production the Docker image builds the React frontend and this backend serves it
# directly (see Dockerfile / docker-compose.yml) — one container, one port, no CORS
# needed at runtime. In local dev this directory doesn't exist (the frontend is served
# separately by `npm run dev` on :5173, proxying /api to this backend), so the catch-all
# route below is simply not registered and every request keeps hitting the API/FastAPI's
# own 404 as before.
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST_DIR.is_dir():
    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_catch_all(full_path: str):
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # Any other path (client-side routes, a page refresh on a deep link) falls back
        # to the SPA shell so react-router can resolve it.
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
