from __future__ import annotations

import os
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session

from database import get_session
from models.models import ValidationRun, Project, MappingConfig
from utils import errors
from utils.storage_paths import project_export_dir
from exporters.excel_exporter import export_full_report, export_single_csv
from api.results import TAB_FILES

router = APIRouter(prefix="/api/projects/{project_id}/runs/{run_id}/export", tags=["export"])


def _get_completed_run(session: Session, project_id: str, run_id: str) -> ValidationRun:
    run = session.get(ValidationRun, run_id)
    if not run or run.project_id != project_id:
        raise errors.not_found("Validation run")
    if run.status != "completed":
        raise errors.bad_request("This validation run has not completed yet, so there is nothing to export.")
    return run


@router.get("/excel")
def export_excel(project_id: str, run_id: str, session: Session = Depends(get_session)):
    run = _get_completed_run(session, project_id, run_id)
    project = session.get(Project, project_id)
    mc = session.get(MappingConfig, run.mapping_id)

    files = {k: os.path.join(run.result_dir, v) for k, v in TAB_FILES.items()}
    out_path = os.path.join(project_export_dir(project_id), f"migration_report_{run_id[:8]}.xlsx")
    export_full_report(out_path, project.name, mc.name, run.summary_json, files)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{project.name.replace(' ', '_')}_migration_report.xlsx",
    )


@router.get("/csv/{tab}")
def export_csv(project_id: str, run_id: str, tab: str, session: Session = Depends(get_session)):
    if tab not in TAB_FILES:
        raise errors.bad_request(f"Unknown results tab '{tab}'.")
    run = _get_completed_run(session, project_id, run_id)
    parquet_path = os.path.join(run.result_dir, TAB_FILES[tab])
    out_path = os.path.join(project_export_dir(project_id), f"{tab}_{uuid.uuid4().hex[:8]}.csv")
    export_single_csv(parquet_path, out_path)
    return FileResponse(out_path, media_type="text/csv", filename=f"{tab}.csv")
