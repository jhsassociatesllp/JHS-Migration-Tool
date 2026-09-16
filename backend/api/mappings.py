from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_session
from models.models import Project, UploadedFile, MappingConfig, MappingTemplate
from api.schemas import MappingConfigCreate, MappingConfigUpdate, TemplateCreate
from utils import errors
from services.mapping_suggester import suggest_mappings

router = APIRouter(prefix="/api/projects/{project_id}", tags=["mappings"])


def _get_file_or_404(session: Session, project_id: str, file_id: str) -> UploadedFile:
    f = session.get(UploadedFile, file_id)
    if not f or f.project_id != project_id:
        raise errors.not_found("File")
    return f


@router.get("/mapping-suggestions")
def get_suggestions(project_id: str, source_file_id: str, target_file_id: str, session: Session = Depends(get_session)):
    src = _get_file_or_404(session, project_id, source_file_id)
    tgt = _get_file_or_404(session, project_id, target_file_id)
    if src.status != "inspected" or tgt.status != "inspected":
        raise errors.bad_request("Both files must be successfully inspected before mappings can be suggested.")
    suggestions = suggest_mappings(list(src.columns_json.keys()), list(tgt.columns_json.keys()))
    return {
        "source_columns": src.columns_json,
        "target_columns": tgt.columns_json,
        "suggestions": suggestions,
    }


@router.get("/mappings")
def list_mappings(project_id: str, session: Session = Depends(get_session)):
    return session.exec(select(MappingConfig).where(MappingConfig.project_id == project_id)).all()


@router.post("/mappings")
def create_mapping(project_id: str, payload: MappingConfigCreate, session: Session = Depends(get_session)):
    if not session.get(Project, project_id):
        raise errors.not_found("Project")
    src = _get_file_or_404(session, project_id, payload.source_file_id)
    tgt = _get_file_or_404(session, project_id, payload.target_file_id)

    _validate_mapping_columns(payload.column_mappings, src, tgt)

    mc = MappingConfig(
        project_id=project_id,
        name=payload.name,
        source_file_id=payload.source_file_id,
        target_file_id=payload.target_file_id,
        column_mappings_json=[m.dict() for m in payload.column_mappings],
        normalization_json=payload.normalization.dict(),
        validation_rules_json=payload.validation_rules or {
            "record_existence": True,
            "duplicate_detection": True,
            "field_level_comparison": True,
            "null_validation": True,
            "data_type_validation": True,
        },
        parent_mapping_id=payload.parent_mapping_id,
    )
    session.add(mc)
    session.commit()
    session.refresh(mc)
    return mc


def _validate_mapping_columns(mappings, src: UploadedFile, tgt: UploadedFile):
    src_cols = set(src.columns_json.keys())
    tgt_cols = set(tgt.columns_json.keys())
    if not any(m.is_matching_key for m in mappings):
        raise errors.bad_request(
            "At least one mapped field must be marked as a matching key before this mapping can be saved."
        )
    for m in mappings:
        for c in m.source_columns:
            if c not in src_cols:
                raise errors.missing_column(c, src.original_filename)
        if m.target_column not in tgt_cols:
            raise errors.missing_column(m.target_column, tgt.original_filename)


@router.get("/mappings/{mapping_id}")
def get_mapping(project_id: str, mapping_id: str, session: Session = Depends(get_session)):
    mc = session.get(MappingConfig, mapping_id)
    if not mc or mc.project_id != project_id:
        raise errors.not_found("Mapping")
    return mc


@router.patch("/mappings/{mapping_id}")
def update_mapping(project_id: str, mapping_id: str, payload: MappingConfigUpdate, session: Session = Depends(get_session)):
    mc = session.get(MappingConfig, mapping_id)
    if not mc or mc.project_id != project_id:
        raise errors.not_found("Mapping")
    if payload.name is not None:
        mc.name = payload.name
    if payload.column_mappings is not None:
        src = _get_file_or_404(session, project_id, mc.source_file_id)
        tgt = _get_file_or_404(session, project_id, mc.target_file_id)
        _validate_mapping_columns(payload.column_mappings, src, tgt)
        mc.column_mappings_json = [m.dict() for m in payload.column_mappings]
    if payload.normalization is not None:
        mc.normalization_json = payload.normalization.dict()
    if payload.validation_rules is not None:
        mc.validation_rules_json = payload.validation_rules
    mc.updated_at = datetime.utcnow()
    session.add(mc)
    session.commit()
    session.refresh(mc)
    return mc


@router.delete("/mappings/{mapping_id}")
def delete_mapping(project_id: str, mapping_id: str, session: Session = Depends(get_session)):
    mc = session.get(MappingConfig, mapping_id)
    if not mc or mc.project_id != project_id:
        raise errors.not_found("Mapping")
    session.delete(mc)
    session.commit()
    return {"ok": True}


# ---- Mapping templates (reusable across projects/uploads) ----

templates_router = APIRouter(prefix="/api/mapping-templates", tags=["mapping-templates"])


@templates_router.get("")
def list_templates(project_id: str | None = None, session: Session = Depends(get_session)):
    q = select(MappingTemplate)
    if project_id:
        q = q.where(MappingTemplate.project_id == project_id)
    return session.exec(q.order_by(MappingTemplate.created_at.desc())).all()


@templates_router.post("")
def create_template(payload: TemplateCreate, session: Session = Depends(get_session)):
    t = MappingTemplate(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        column_mappings_json=[m.dict() for m in payload.column_mappings],
        normalization_json=payload.normalization.dict(),
        validation_rules_json=payload.validation_rules or {},
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@templates_router.post("/{template_id}/duplicate")
def duplicate_template(template_id: str, session: Session = Depends(get_session)):
    t = session.get(MappingTemplate, template_id)
    if not t:
        raise errors.not_found("Mapping template")
    copy = MappingTemplate(
        project_id=t.project_id,
        name=f"{t.name} (copy)",
        description=t.description,
        column_mappings_json=t.column_mappings_json,
        normalization_json=t.normalization_json,
        validation_rules_json=t.validation_rules_json,
    )
    session.add(copy)
    session.commit()
    session.refresh(copy)
    return copy


@templates_router.delete("/{template_id}")
def delete_template(template_id: str, session: Session = Depends(get_session)):
    t = session.get(MappingTemplate, template_id)
    if not t:
        raise errors.not_found("Mapping template")
    session.delete(t)
    session.commit()
    return {"ok": True}
