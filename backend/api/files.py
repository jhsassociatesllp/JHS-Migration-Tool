from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends, UploadFile, File
from sqlmodel import Session, select

from database import get_session
from models.models import Project, UploadedFile
from api.schemas import FileRoleUpdate
from utils import errors
from utils.storage_paths import safe_filename, project_upload_dir, project_parquet_dir
from services.file_inspector import inspect_csv, read_preview_rows, FileInspectionError

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])

CHUNK_SIZE = 1024 * 1024  # 1MB streamed write, keeps large uploads out of memory


@router.get("")
def list_files(project_id: str, session: Session = Depends(get_session)):
    if not session.get(Project, project_id):
        raise errors.not_found("Project")
    return session.exec(select(UploadedFile).where(UploadedFile.project_id == project_id)).all()


@router.post("")
async def upload_file(project_id: str, file: UploadFile = File(...), session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise errors.not_found("Project")

    stored_name = safe_filename(file.filename)
    dest_dir = project_upload_dir(project_id)
    dest_path = os.path.join(dest_dir, stored_name)

    size = 0
    with open(dest_path, "wb") as out:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

    record = UploadedFile(
        project_id=project_id,
        original_filename=file.filename,
        stored_filename=stored_name,
        file_size_bytes=size,
        status="uploaded",
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    # Inspect immediately (streamed via DuckDB — safe for large files) so the
    # user sees row/column counts and a preview right away.
    _inspect_and_persist(record, session)
    return record


def _inspect_and_persist(record: UploadedFile, session: Session):
    dest_path = os.path.join(project_upload_dir(record.project_id), record.stored_filename)
    parquet_path = os.path.join(project_parquet_dir(record.project_id), record.id + ".parquet")
    try:
        result = inspect_csv(dest_path, parquet_out_path=parquet_path)
        record.row_count = result.row_count
        record.column_count = result.column_count
        record.encoding = result.encoding
        record.delimiter = result.delimiter
        record.has_bom = result.has_bom
        record.columns_json = result.columns
        record.parse_warnings_json = result.warnings
        record.status = "inspected"
        record.error_message = None
    except FileInspectionError as e:
        record.status = "error"
        record.error_message = str(e)
    session.add(record)
    session.commit()
    session.refresh(record)


@router.get("/{file_id}")
def get_file(project_id: str, file_id: str, session: Session = Depends(get_session)):
    record = session.get(UploadedFile, file_id)
    if not record or record.project_id != project_id:
        raise errors.not_found("File")
    return record


@router.get("/{file_id}/preview")
def preview_file(project_id: str, file_id: str, rows: int = 50, session: Session = Depends(get_session)):
    record = session.get(UploadedFile, file_id)
    if not record or record.project_id != project_id:
        raise errors.not_found("File")
    if record.status != "inspected":
        raise errors.bad_request(record.error_message or "This file has not been successfully inspected yet.")

    parquet_path = os.path.join(project_parquet_dir(project_id), record.id + ".parquet")
    source_path = parquet_path if os.path.exists(parquet_path) else os.path.join(project_upload_dir(project_id), record.stored_filename)

    try:
        preview_rows = read_preview_rows(source_path, min(rows, 500), delimiter=record.delimiter or ",")
    except Exception as e:
        raise errors.bad_request(f"Could not generate a preview for '{record.original_filename}'. Detail: {e}")
    return {
        "columns": record.columns_json,
        "rows": preview_rows,
        "row_count": record.row_count,
        "warnings": record.parse_warnings_json,
    }


@router.patch("/{file_id}/role")
def set_role(project_id: str, file_id: str, payload: FileRoleUpdate, session: Session = Depends(get_session)):
    if payload.role not in ("source", "target", "unassigned"):
        raise errors.bad_request("Role must be one of: source, target, unassigned.")
    record = session.get(UploadedFile, file_id)
    if not record or record.project_id != project_id:
        raise errors.not_found("File")
    record.role = payload.role
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.delete("/{file_id}")
def delete_file(project_id: str, file_id: str, session: Session = Depends(get_session)):
    record = session.get(UploadedFile, file_id)
    if not record or record.project_id != project_id:
        raise errors.not_found("File")

    path = os.path.join(project_upload_dir(project_id), record.stored_filename)
    if os.path.exists(path):
        os.remove(path)
    parquet_path = os.path.join(project_parquet_dir(project_id), record.id + ".parquet")
    if os.path.exists(parquet_path):
        os.remove(parquet_path)

    session.delete(record)
    session.commit()
    return {"ok": True}
