from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class FileRoleUpdate(BaseModel):
    role: str  # source | target | unassigned


class FieldMappingIn(BaseModel):
    source_columns: list[str]
    target_column: str
    data_type: str = "string"
    transform: str = "none"
    required: bool = False
    is_matching_key: bool = False
    compare_in_validation: bool = True


class NormalizationIn(BaseModel):
    trim: bool = True
    case_insensitive: bool = True
    null_tokens: list[str] = ["", "NULL", "null", "N/A", "n/a", "NA", "na", "None"]
    numeric_normalize: bool = True
    date_normalize: bool = True


class MappingConfigCreate(BaseModel):
    name: str
    source_file_id: str
    target_file_id: str
    column_mappings: list[FieldMappingIn]
    normalization: NormalizationIn = NormalizationIn()
    validation_rules: Optional[dict] = None
    parent_mapping_id: Optional[str] = None


class MappingConfigUpdate(BaseModel):
    name: Optional[str] = None
    column_mappings: Optional[list[FieldMappingIn]] = None
    normalization: Optional[NormalizationIn] = None
    validation_rules: Optional[dict] = None


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    column_mappings: list[FieldMappingIn]
    normalization: NormalizationIn = NormalizationIn()
    validation_rules: Optional[dict] = None


class RunCreate(BaseModel):
    mapping_id: str
