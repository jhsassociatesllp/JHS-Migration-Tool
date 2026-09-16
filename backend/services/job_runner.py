"""Simple in-process background job execution for validation runs.

Kept intentionally simple for the MVP per the spec ("keep the architecture
simple"): a bounded thread pool executes each run so the HTTP request that
kicks it off returns immediately, and the frontend polls run status/progress.
For a multi-process production deployment this executor could be swapped
for Celery/RQ without changing the engine or API contract.
"""
from __future__ import annotations

import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlmodel import Session

from database import engine
from models.models import ValidationRun, MappingConfig, UploadedFile
from validators.engine import EngineConfig, FieldMapping, run_validation, EngineError
from utils.storage_paths import project_parquet_dir, run_result_dir

_executor = ThreadPoolExecutor(max_workers=2)


def _build_engine_config(mc: MappingConfig) -> EngineConfig:
    fields = [
        FieldMapping(
            source_columns=m["source_columns"],
            target_column=m["target_column"],
            data_type=m.get("data_type", "string"),
            transform=m.get("transform", "none"),
            required=m.get("required", False),
            is_matching_key=m.get("is_matching_key", False),
            compare_in_validation=m.get("compare_in_validation", True),
        )
        for m in mc.column_mappings_json
    ]
    norm = mc.normalization_json or {}
    kwargs = dict(
        fields=fields,
        trim=norm.get("trim", True),
        case_insensitive=norm.get("case_insensitive", True),
        numeric_normalize=norm.get("numeric_normalize", True),
        date_normalize=norm.get("date_normalize", True),
    )
    if norm.get("null_tokens"):
        kwargs["null_tokens"] = norm["null_tokens"]
    return EngineConfig(**kwargs)


def _update_progress(run_id: str, pct: int, message: str):
    with Session(engine) as session:
        run = session.get(ValidationRun, run_id)
        if run:
            run.progress_percent = pct
            run.current_operation = message
            session.add(run)
            session.commit()


def _execute(run_id: str):
    with Session(engine) as session:
        run = session.get(ValidationRun, run_id)
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.utcnow()
        session.add(run)
        session.commit()

        mc = session.get(MappingConfig, run.mapping_id)
        src_file = session.get(UploadedFile, mc.source_file_id)
        tgt_file = session.get(UploadedFile, mc.target_file_id)
        project_id = run.project_id

    src_parquet = os.path.join(project_parquet_dir(project_id), src_file.id + ".parquet")
    tgt_parquet = os.path.join(project_parquet_dir(project_id), tgt_file.id + ".parquet")
    out_dir = run_result_dir(project_id, run_id)

    t0 = time.time()
    try:
        cfg = _build_engine_config(mc)
        result = run_validation(
            src_parquet, tgt_parquet, cfg, out_dir,
            progress_cb=lambda pct, msg: _update_progress(run_id, pct, msg),
        )
        with Session(engine) as session:
            run = session.get(ValidationRun, run_id)
            run.status = "completed"
            run.progress_percent = 100
            run.current_operation = "Completed"
            run.summary_json = result.summary
            run.result_dir = out_dir
            run.completed_at = datetime.utcnow()
            run.duration_seconds = round(time.time() - t0, 2)
            session.add(run)
            session.commit()
    except EngineError as e:
        with Session(engine) as session:
            run = session.get(ValidationRun, run_id)
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()
    except Exception:
        err_text = traceback.format_exc(limit=3)
        with Session(engine) as session:
            run = session.get(ValidationRun, run_id)
            run.status = "failed"
            run.error_message = (
                "Validation failed due to an unexpected error while processing the data. "
                "Please check that both files and the mapping configuration are still valid."
            )
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()
        print(err_text)


def submit_run(run_id: str):
    _executor.submit(_execute, run_id)
