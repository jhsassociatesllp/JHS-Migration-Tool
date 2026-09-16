from __future__ import annotations

import shutil
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_session
from models.models import Project, UploadedFile, MappingConfig, ValidationRun
from api.schemas import ProjectCreate, ProjectUpdate
from utils import errors
from utils.storage_paths import UPLOADS_DIR, PARQUET_DIR, RESULTS_DIR
import os

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects(session: Session = Depends(get_session)):
    projects = session.exec(select(Project).order_by(Project.updated_at.desc())).all()
    out = []
    for p in projects:
        file_count = len(session.exec(select(UploadedFile).where(UploadedFile.project_id == p.id)).all())
        run_count = len(session.exec(select(ValidationRun).where(ValidationRun.project_id == p.id)).all())
        out.append({**p.dict(), "file_count": file_count, "run_count": run_count})
    return out


@router.post("")
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    project = Project(name=payload.name, description=payload.description)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise errors.not_found("Project")
    return project


@router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise errors.not_found("Project")
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise errors.not_found("Project")

    for run in session.exec(select(ValidationRun).where(ValidationRun.project_id == project_id)).all():
        session.delete(run)
    for mc in session.exec(select(MappingConfig).where(MappingConfig.project_id == project_id)).all():
        session.delete(mc)
    for f in session.exec(select(UploadedFile).where(UploadedFile.project_id == project_id)).all():
        session.delete(f)
    session.delete(project)
    session.commit()

    for base in (UPLOADS_DIR, PARQUET_DIR, RESULTS_DIR):
        d = os.path.join(base, project_id)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)

    return {"ok": True}
