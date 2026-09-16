"""
Core persistence models for the Migration Validation Tool.

Design notes
------------
- SQLite (via SQLModel) stores CONFIGURATION and METADATA only:
  projects, file metadata, mapping configs, validation run summaries.
- It never stores bulk row-level data. Row-level source/target data lives
  in DuckDB-queryable Parquet files on disk (see services/storage_paths.py).
- A project can hold MANY file-pairs / mapping configs (not just one),
  so the schema supports N source tables -> M target tables from day one,
  even though the Phase 1 UI drives one mapping at a time.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, JSON, Column


def new_id() -> str:
    return uuid.uuid4().hex


class Project(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UploadedFile(SQLModel, table=True):
    """Metadata about an uploaded CSV. The actual CSV is kept on disk;
    a DuckDB-friendly Parquet copy is generated for fast repeated queries."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    original_filename: str
    stored_filename: str  # sanitized name on disk
    role: str = Field(default="unassigned")  # source | target | unassigned
    file_size_bytes: int = 0
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    encoding: Optional[str] = None
    delimiter: Optional[str] = None
    has_bom: bool = False
    columns_json: dict = Field(default_factory=dict, sa_column=Column(JSON))  # {col_name: inferred_dtype}
    parse_warnings_json: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="uploaded")  # uploaded | inspected | error
    error_message: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class MappingConfig(SQLModel, table=True):
    """A configured source-file <-> target-file mapping: column mappings,
    matching keys, and validation rule toggles. A project may contain many
    of these (one per source/target table pair) to support multi-table
    migrations."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    name: str
    source_file_id: str = Field(foreign_key="uploadedfile.id")
    target_file_id: str = Field(foreign_key="uploadedfile.id")

    # list[{ source_columns: [str], target_column: str, transform: str,
    #        data_type: str, required: bool, is_matching_key: bool,
    #        compare_in_validation: bool }]
    column_mappings_json: list = Field(default_factory=list, sa_column=Column(JSON))

    # {"null_tokens": [...], "case_insensitive": bool, "trim": bool, ...} global defaults
    normalization_json: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # which validations are enabled for this mapping
    validation_rules_json: dict = Field(
        default_factory=lambda: {
            "record_existence": True,
            "duplicate_detection": True,
            "field_level_comparison": True,
            "null_validation": True,
            "data_type_validation": True,
        },
        sa_column=Column(JSON),
    )

    # optional referential-integrity link to a parent MappingConfig, e.g.
    # this mapping's target FK must exist in the parent mapping's target key
    parent_mapping_id: Optional[str] = Field(default=None, foreign_key="mappingconfig.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MappingTemplate(SQLModel, table=True):
    """A reusable, named mapping definition the user can save and re-apply
    to a fresh pair of files later (e.g. across monthly migration runs)."""
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: Optional[str] = Field(default=None, foreign_key="project.id", index=True)
    name: str
    description: Optional[str] = None
    column_mappings_json: list = Field(default_factory=list, sa_column=Column(JSON))
    normalization_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    validation_rules_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ValidationRun(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    mapping_id: str = Field(foreign_key="mappingconfig.id", index=True)
    status: str = Field(default="queued")  # queued | running | completed | failed
    progress_percent: int = 0
    current_operation: Optional[str] = None
    error_message: Optional[str] = None

    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # {"source_rows":..,"target_rows":..,"matched":..,"missing":..,"extra":..,
    #  "changed":..,"duplicates_source":..,"duplicates_target":..,
    #  "unique_source":..,"unique_target":.. }

    result_dir: Optional[str] = None  # folder holding parquet outputs for this run

    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
