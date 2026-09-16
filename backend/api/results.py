from __future__ import annotations

import os
import duckdb
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from database import get_session
from models.models import ValidationRun, MappingConfig, UploadedFile
from utils import errors
from utils.storage_paths import project_parquet_dir
from validators.engine import EngineConfig, FieldMapping, build_key_expr, _raw_expr, _norm_expr

router = APIRouter(prefix="/api/projects/{project_id}/runs/{run_id}/results", tags=["results"])

TAB_FILES = {
    "missing": "missing.parquet",
    "extra": "extra.parquet",
    "changed": "changed_keys.parquet",
    "field_diffs": "field_diffs.parquet",
    "duplicates_source": "duplicates_source.parquet",
    "duplicates_target": "duplicates_target.parquet",
}


def _get_run(session: Session, project_id: str, run_id: str) -> ValidationRun:
    run = session.get(ValidationRun, run_id)
    if not run or run.project_id != project_id:
        raise errors.not_found("Validation run")
    if run.status != "completed":
        raise errors.bad_request(f"This validation run has status '{run.status}' — results are not yet available.")
    return run


@router.get("/{tab}")
def get_tab_results(
    project_id: str,
    run_id: str,
    tab: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    search: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    session: Session = Depends(get_session),
):
    if tab not in TAB_FILES:
        raise errors.bad_request(f"Unknown results tab '{tab}'.")
    run = _get_run(session, project_id, run_id)
    path = os.path.join(run.result_dir, TAB_FILES[tab])
    if not os.path.exists(path):
        return {"columns": [], "rows": [], "total": 0, "page": page, "page_size": page_size}

    con = duckdb.connect()
    base = f"read_parquet('{path}')"
    cols = [d[0] for d in con.execute(f"SELECT * FROM {base} LIMIT 0").description]

    where = ""
    if search:
        esc = search.replace("'", "''")
        conds = " OR ".join(f"CAST({c} AS VARCHAR) ILIKE '%{esc}%'" for c in cols) if cols else "FALSE"
        where = f"WHERE {conds}"

    total = con.execute(f"SELECT COUNT(*) FROM {base} {where}").fetchone()[0]

    order = ""
    if sort_by and sort_by in cols:
        order = f'ORDER BY "{sort_by}" {"ASC" if sort_dir == "asc" else "DESC"}'

    offset = (page - 1) * page_size
    rows_df = con.execute(f"SELECT * FROM {base} {where} {order} LIMIT {page_size} OFFSET {offset}").fetchdf()
    rows = rows_df.astype(object).where(rows_df.notnull(), None).to_dict(orient="records")
    con.close()

    return {"columns": cols, "rows": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/record/{matching_key}")
def get_record_detail(project_id: str, run_id: str, matching_key: str, session: Session = Depends(get_session)):
    """Full field-by-field comparison for a single logical record (all
    compared fields, including ones that matched) plus the raw source and
    target rows — computed on demand so we don't have to persist a wide
    diff table for every matched record up front."""
    run = _get_run(session, project_id, run_id)
    mc = session.get(MappingConfig, run.mapping_id)
    src_file = session.get(UploadedFile, mc.source_file_id)
    tgt_file = session.get(UploadedFile, mc.target_file_id)

    src_parquet = os.path.join(project_parquet_dir(project_id), src_file.id + ".parquet")
    tgt_parquet = os.path.join(project_parquet_dir(project_id), tgt_file.id + ".parquet")

    fields = [
        FieldMapping(
            source_columns=m["source_columns"], target_column=m["target_column"],
            data_type=m.get("data_type", "string"), transform=m.get("transform", "none"),
            required=m.get("required", False), is_matching_key=m.get("is_matching_key", False),
            compare_in_validation=m.get("compare_in_validation", True),
        )
        for m in mc.column_mappings_json
    ]
    norm = mc.normalization_json or {}
    cfg = EngineConfig(
        fields=fields, trim=norm.get("trim", True), case_insensitive=norm.get("case_insensitive", True),
        numeric_normalize=norm.get("numeric_normalize", True), date_normalize=norm.get("date_normalize", True),
    )
    if norm.get("null_tokens"):
        cfg.null_tokens = norm["null_tokens"]

    con = duckdb.connect()
    con.execute(f"CREATE VIEW src AS SELECT * FROM read_parquet('{src_parquet}')")
    con.execute(f"CREATE VIEW tgt AS SELECT * FROM read_parquet('{tgt_parquet}')")
    src_key = build_key_expr("src", "source", cfg)
    tgt_key = build_key_expr("tgt", "target", cfg)
    esc_key = matching_key.replace("'", "''")

    src_rows_df = con.execute(f"SELECT * FROM (SELECT *, {src_key} AS __key FROM src) WHERE __key = '{esc_key}'").fetchdf()
    tgt_rows_df = con.execute(f"SELECT * FROM (SELECT *, {tgt_key} AS __key FROM tgt) WHERE __key = '{esc_key}'").fetchdf()

    def clean(df):
        df = df.drop(columns=["__key"], errors="ignore")
        return df.astype(object).where(df.notnull(), None).to_dict(orient="records")

    src_rows = clean(src_rows_df)
    tgt_rows = clean(tgt_rows_df)

    field_comparison = []
    if len(src_rows) == 1 and len(tgt_rows) == 1:
        for f in fields:
            if f.is_matching_key:
                continue
            s_raw = _raw_expr("s", f.source_columns, f.transform, cfg.key_separator)
            t_raw = _raw_expr("t", [f.target_column], f.transform, cfg.key_separator)
            s_norm = _norm_expr(s_raw, f.data_type, cfg)
            t_norm = _norm_expr(t_raw, f.data_type, cfg)
            status_expr = (
                f"CASE WHEN {s_norm} IS NULL AND {t_norm} IS NULL THEN 'MATCH' "
                f"WHEN {s_norm} IS NULL AND {t_norm} IS NOT NULL THEN 'NULL_IN_SOURCE' "
                f"WHEN {s_norm} IS NOT NULL AND {t_norm} IS NULL THEN 'NULL_IN_TARGET' "
                f"WHEN {s_norm} = {t_norm} THEN 'MATCH' ELSE 'CHANGED' END"
            )
            row = con.execute(
                f"SELECT CAST({s_raw} AS VARCHAR), CAST({t_raw} AS VARCHAR), {status_expr} "
                f"FROM (SELECT *, {src_key} AS __key FROM src) s, (SELECT *, {tgt_key} AS __key FROM tgt) t "
                f"WHERE s.__key = '{esc_key}' AND t.__key = '{esc_key}'"
            ).fetchone()
            field_comparison.append(
                {"field": f.target_column, "source_value": row[0], "target_value": row[1], "status": row[2]}
            )
    con.close()

    return {
        "matching_key": matching_key,
        "source_records": src_rows,
        "target_records": tgt_rows,
        "field_comparison": field_comparison,
        "ambiguous": len(src_rows) != 1 or len(tgt_rows) != 1,
    }
