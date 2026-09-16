from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_session
from models.models import Project, MappingConfig, ValidationRun
from api.schemas import RunCreate
from utils import errors
from services.job_runner import submit_run

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["validation"])


@router.get("")
def list_runs(project_id: str, session: Session = Depends(get_session)):
    return session.exec(
        select(ValidationRun).where(ValidationRun.project_id == project_id).order_by(ValidationRun.started_at.desc())
    ).all()


@router.post("")
def start_run(project_id: str, payload: RunCreate, session: Session = Depends(get_session)):
    if not session.get(Project, project_id):
        raise errors.not_found("Project")
    mc = session.get(MappingConfig, payload.mapping_id)
    if not mc or mc.project_id != project_id:
        raise errors.not_found("Mapping configuration")

    run = ValidationRun(project_id=project_id, mapping_id=mc.id, status="queued", progress_percent=0)
    session.add(run)
    session.commit()
    session.refresh(run)

    submit_run(run.id)
    return run


@router.get("/{run_id}")
def get_run(project_id: str, run_id: str, session: Session = Depends(get_session)):
    run = session.get(ValidationRun, run_id)
    if not run or run.project_id != project_id:
        raise errors.not_found("Validation run")
    return run


@router.get("/{run_id}/compare/{other_run_id}")
def compare_runs(project_id: str, run_id: str, other_run_id: str, session: Session = Depends(get_session)):
    run_a = session.get(ValidationRun, run_id)
    run_b = session.get(ValidationRun, other_run_id)
    if not run_a or run_a.project_id != project_id or not run_b or run_b.project_id != project_id:
        raise errors.not_found("Validation run")

    keys = set(run_a.summary_json.keys()) | set(run_b.summary_json.keys())
    diff = {
        k: {
            "run_a": run_a.summary_json.get(k),
            "run_b": run_b.summary_json.get(k),
            "delta": (run_b.summary_json.get(k) or 0) - (run_a.summary_json.get(k) or 0),
        }
        for k in sorted(keys)
    }
    return {"run_a": run_a, "run_b": run_b, "diff": diff}


@router.delete("/{run_id}")
def delete_run(project_id: str, run_id: str, session: Session = Depends(get_session)):
    import shutil
    run = session.get(ValidationRun, run_id)
    if not run or run.project_id != project_id:
        raise errors.not_found("Validation run")
    if run.result_dir:
        shutil.rmtree(run.result_dir, ignore_errors=True)
    session.delete(run)
    session.commit()
    return {"ok": True}
