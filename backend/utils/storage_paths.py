"""Centralised, safe path handling so uploaded/generated files are always
isolated per-project and never trust user-supplied filenames directly."""
from __future__ import annotations

import os
import re
import uuid

STORAGE_ROOT = os.path.abspath(
    os.environ.get("APP_STORAGE_ROOT", os.path.join(os.path.dirname(__file__), "..", "..", "storage"))
)

UPLOADS_DIR = os.path.join(STORAGE_ROOT, "uploads")
PARQUET_DIR = os.path.join(STORAGE_ROOT, "parquet")
RESULTS_DIR = os.path.join(STORAGE_ROOT, "results")
EXPORTS_DIR = os.path.join(STORAGE_ROOT, "exports")
TEMPLATES_DIR = os.path.join(STORAGE_ROOT, "templates")

for _d in (UPLOADS_DIR, PARQUET_DIR, RESULTS_DIR, EXPORTS_DIR, TEMPLATES_DIR):
    os.makedirs(_d, exist_ok=True)

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(original_name: str) -> str:
    """Never trust the client's filename. Strip path components, collapse
    unsafe characters, and prefix with a random id to prevent collisions
    and directory traversal."""
    base = os.path.basename(original_name or "file.csv")
    base = _SAFE_CHARS.sub("_", base)
    if not base:
        base = "file.csv"
    return f"{uuid.uuid4().hex[:12]}_{base}"


def project_upload_dir(project_id: str) -> str:
    d = os.path.join(UPLOADS_DIR, project_id)
    os.makedirs(d, exist_ok=True)
    return d


def project_parquet_dir(project_id: str) -> str:
    d = os.path.join(PARQUET_DIR, project_id)
    os.makedirs(d, exist_ok=True)
    return d


def run_result_dir(project_id: str, run_id: str) -> str:
    d = os.path.join(RESULTS_DIR, project_id, run_id)
    os.makedirs(d, exist_ok=True)
    return d


def project_export_dir(project_id: str) -> str:
    d = os.path.join(EXPORTS_DIR, project_id)
    os.makedirs(d, exist_ok=True)
    return d
