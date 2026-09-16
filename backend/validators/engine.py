"""
Core migration-validation engine.

Everything here runs as SQL inside DuckDB against Parquet files on disk —
no full dataset is ever materialised as a Python object, so this scales to
multi-million-row files. Only small aggregate results (summaries, diffs,
duplicate lists) are pulled back into Python/Parquet outputs.

Column identifiers are always taken from values already recorded in the
database (the file's own inspected column list) — never interpolated
directly from arbitrary free-text user input — and are still defensively
quoted before being placed into SQL strings.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import duckdb


DEFAULT_NULL_TOKENS = ["", "NULL", "null", "Null", "N/A", "n/a", "NA", "na", "None", "NONE", "#N/A"]

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
]


class EngineError(Exception):
    """User-facing error raised when a mapping/config problem prevents validation."""


def q(identifier: str) -> str:
    """Safely quote a SQL identifier."""
    return '"' + str(identifier).replace('"', '""') + '"'


def _sql_str_list(values: list[str]) -> str:
    esc = [v.replace("'", "''") for v in values]
    return "(" + ",".join(f"'{v}'" for v in esc) + ")"


@dataclass
class FieldMapping:
    source_columns: list[str]
    target_column: str
    data_type: str = "string"  # string | numeric | date
    transform: str = "none"  # none | upper | lower | concat
    required: bool = False
    is_matching_key: bool = False
    compare_in_validation: bool = True


@dataclass
class EngineConfig:
    fields: list[FieldMapping]
    trim: bool = True
    case_insensitive: bool = True
    null_tokens: list = field(default_factory=lambda: list(DEFAULT_NULL_TOKENS))
    numeric_normalize: bool = True
    date_normalize: bool = True
    key_separator: str = "||~||"


def _raw_expr(alias: str, cols: list[str], transform: str, sep: str) -> str:
    """Build the raw (pre-normalisation) SQL expression for one logical
    field, supporting many-source-columns -> one-target-column concatenation."""
    parts = [f"{alias}.{q(c)}" for c in cols]
    if len(parts) == 1:
        raw = f"CAST({parts[0]} AS VARCHAR)"
    else:
        raw = "CONCAT_WS(' ', " + ", ".join(f"CAST({p} AS VARCHAR)" for p in parts) + ")"
    if transform == "upper":
        raw = f"UPPER({raw})"
    elif transform == "lower":
        raw = f"LOWER({raw})"
    return raw


def _norm_expr(raw_expr: str, data_type: str, cfg: EngineConfig) -> str:
    """Wrap a raw value expression with configured normalisation rules,
    producing a NULL-safe, comparable VARCHAR expression."""
    e = raw_expr
    if cfg.trim:
        e = f"TRIM({e})"

    null_list = _sql_str_list(cfg.null_tokens)
    e = f"NULLIF({e}, NULL)"  # no-op placeholder to keep chain uniform
    e = f"CASE WHEN TRIM({raw_expr}) IN {null_list} THEN NULL ELSE {e} END"

    if data_type == "numeric" and cfg.numeric_normalize:
        # Strip to a canonical numeric string: 001234 / 1234 / 1234.0 -> "1234"
        e = (
            f"CASE WHEN {e} IS NULL THEN NULL "
            f"WHEN TRY_CAST({e} AS DOUBLE) IS NOT NULL "
            f"THEN CASE WHEN TRY_CAST({e} AS DOUBLE) = CAST(TRY_CAST({e} AS DOUBLE) AS BIGINT) "
            f"THEN CAST(CAST(TRY_CAST({e} AS DOUBLE) AS BIGINT) AS VARCHAR) "
            f"ELSE CAST(TRY_CAST({e} AS DOUBLE) AS VARCHAR) END "
            f"ELSE {('UPPER(' + e + ')') if cfg.case_insensitive else e} END"
        )
    elif data_type == "date" and cfg.date_normalize:
        cast_chain = e
        for fmt in DATE_FORMATS:
            cast_chain = f"COALESCE(TRY_STRPTIME({e}, '{fmt}'), {cast_chain if cast_chain != e else 'NULL'})"
        # Simpler & robust: try each format in order via COALESCE of TRY_STRPTIME
        attempts = ", ".join(f"TRY_STRPTIME({e}, '{fmt}')" for fmt in DATE_FORMATS)
        e = f"CASE WHEN {e} IS NULL THEN NULL ELSE CAST(COALESCE({attempts}) AS VARCHAR) END"
    else:
        if cfg.case_insensitive:
            e = f"CASE WHEN {e} IS NULL THEN NULL ELSE UPPER({e}) END"

    return e


def _key_fields(cfg: EngineConfig) -> list[FieldMapping]:
    keys = [f for f in cfg.fields if f.is_matching_key]
    if not keys:
        raise EngineError(
            "No matching key has been configured. Please mark at least one mapped field as a matching key "
            "before running validation."
        )
    return keys


def build_key_expr(alias: str, side: str, cfg: EngineConfig) -> str:
    parts = []
    for f in _key_fields(cfg):
        cols = f.source_columns if side == "source" else [f.target_column]
        raw = _raw_expr(alias, cols, f.transform, cfg.key_separator)
        parts.append(_norm_expr(raw, f.data_type, cfg))
    if len(parts) == 1:
        return f"({parts[0]})"
    return "CONCAT_WS('" + cfg.key_separator + "', " + ", ".join(f"COALESCE({p}, '')" for p in parts) + ")"


def build_key_isnull_expr(alias: str, side: str, cfg: EngineConfig) -> str:
    """True if ANY component of the (possibly composite) key is NULL —
    such rows are excluded from matching and reported separately."""
    checks = []
    for f in _key_fields(cfg):
        cols = f.source_columns if side == "source" else [f.target_column]
        raw = _raw_expr(alias, cols, f.transform, cfg.key_separator)
        checks.append(f"({_norm_expr(raw, f.data_type, cfg)} IS NULL)")
    return " OR ".join(checks)


@dataclass
class RunResult:
    summary: dict
    files: dict  # logical name -> parquet path


def run_validation(
    source_parquet: str,
    target_parquet: str,
    cfg: EngineConfig,
    out_dir: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> RunResult:
    def report(pct: int, msg: str):
        if progress_cb:
            progress_cb(pct, msg)

    if not os.path.exists(source_parquet):
        raise EngineError("The source file's optimized data copy was not found. Please re-upload the source file.")
    if not os.path.exists(target_parquet):
        raise EngineError("The target file's optimized data copy was not found. Please re-upload the target file.")

    os.makedirs(out_dir, exist_ok=True)
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")

    report(2, "Loading source and target datasets")
    con.execute(f"CREATE VIEW src AS SELECT * FROM read_parquet('{source_parquet}')")
    con.execute(f"CREATE VIEW tgt AS SELECT * FROM read_parquet('{target_parquet}')")

    src_key = build_key_expr("src", "source", cfg)
    tgt_key = build_key_expr("tgt", "target", cfg)
    src_key_null = build_key_isnull_expr("src", "source", cfg)
    tgt_key_null = build_key_isnull_expr("tgt", "target", cfg)

    report(8, "Building normalized matching keys")
    con.execute(f"CREATE VIEW src_keyed AS SELECT *, {src_key} AS __key, ({src_key_null}) AS __key_is_null FROM src")
    con.execute(f"CREATE VIEW tgt_keyed AS SELECT *, {tgt_key} AS __key, ({tgt_key_null}) AS __key_is_null FROM tgt")

    source_rows = con.execute("SELECT COUNT(*) FROM src_keyed").fetchone()[0]
    target_rows = con.execute("SELECT COUNT(*) FROM tgt_keyed").fetchone()[0]
    source_null_keys = con.execute("SELECT COUNT(*) FROM src_keyed WHERE __key_is_null").fetchone()[0]
    target_null_keys = con.execute("SELECT COUNT(*) FROM tgt_keyed WHERE __key_is_null").fetchone()[0]

    report(15, "Counting unique customers")
    unique_source = con.execute(
        "SELECT COUNT(DISTINCT __key) FROM src_keyed WHERE NOT __key_is_null"
    ).fetchone()[0]
    unique_target = con.execute(
        "SELECT COUNT(DISTINCT __key) FROM tgt_keyed WHERE NOT __key_is_null"
    ).fetchone()[0]

    report(25, "Identifying duplicate keys")
    dup_source_path = os.path.join(out_dir, "duplicates_source.parquet")
    dup_target_path = os.path.join(out_dir, "duplicates_target.parquet")
    con.execute(
        f"COPY (SELECT __key AS matching_key, COUNT(*) AS source_count "
        f"FROM src_keyed WHERE NOT __key_is_null GROUP BY __key HAVING COUNT(*) > 1 ORDER BY source_count DESC) "
        f"TO '{dup_source_path}' (FORMAT PARQUET)"
    )
    con.execute(
        f"COPY (SELECT __key AS matching_key, COUNT(*) AS target_count "
        f"FROM tgt_keyed WHERE NOT __key_is_null GROUP BY __key HAVING COUNT(*) > 1 ORDER BY target_count DESC) "
        f"TO '{dup_target_path}' (FORMAT PARQUET)"
    )
    dup_source_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{dup_source_path}')").fetchone()[0]
    dup_target_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{dup_target_path}')").fetchone()[0]

    report(35, "Matching source against target")
    src_distinct = "SELECT DISTINCT __key FROM src_keyed WHERE NOT __key_is_null"
    tgt_distinct = "SELECT DISTINCT __key FROM tgt_keyed WHERE NOT __key_is_null"

    matched_count = con.execute(
        f"SELECT COUNT(*) FROM ({src_distinct}) s JOIN ({tgt_distinct}) t ON s.__key = t.__key"
    ).fetchone()[0]

    missing_path = os.path.join(out_dir, "missing.parquet")
    con.execute(
        f"COPY (SELECT src.* EXCLUDE (__key, __key_is_null) FROM src_keyed src "
        f"WHERE NOT __key_is_null AND __key NOT IN ({tgt_distinct})) "
        f"TO '{missing_path}' (FORMAT PARQUET)"
    )
    missing_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{missing_path}')").fetchone()[0]

    report(50, "Finding extra target records")
    extra_path = os.path.join(out_dir, "extra.parquet")
    con.execute(
        f"COPY (SELECT tgt.* EXCLUDE (__key, __key_is_null) FROM tgt_keyed tgt "
        f"WHERE NOT __key_is_null AND __key NOT IN ({src_distinct})) "
        f"TO '{extra_path}' (FORMAT PARQUET)"
    )
    extra_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{extra_path}')").fetchone()[0]

    report(62, "Comparing matched records field by field")
    compare_fields = [f for f in cfg.fields if f.compare_in_validation and not f.is_matching_key]
    field_diff_path = os.path.join(out_dir, "field_diffs.parquet")
    changed_keys_path = os.path.join(out_dir, "changed_keys.parquet")
    changed_count = 0

    if compare_fields:
        # Only unambiguous 1:1 matches (no duplicate key on either side) get
        # field-level compared — ambiguous ones are already surfaced via the
        # duplicate reports instead of being silently guessed at.
        con.execute(
            "CREATE VIEW src_unique AS "
            "SELECT * FROM src_keyed WHERE NOT __key_is_null AND __key IN "
            "(SELECT __key FROM src_keyed WHERE NOT __key_is_null GROUP BY __key HAVING COUNT(*)=1)"
        )
        con.execute(
            "CREATE VIEW tgt_unique AS "
            "SELECT * FROM tgt_keyed WHERE NOT __key_is_null AND __key IN "
            "(SELECT __key FROM tgt_keyed WHERE NOT __key_is_null GROUP BY __key HAVING COUNT(*)=1)"
        )

        union_parts = []
        for f in compare_fields:
            s_raw = _raw_expr("s", f.source_columns, f.transform, cfg.key_separator)
            t_raw = _raw_expr("t", [f.target_column], f.transform, cfg.key_separator)
            s_norm = _norm_expr(s_raw, f.data_type, cfg)
            t_norm = _norm_expr(t_raw, f.data_type, cfg)
            type_check = ""
            if f.data_type == "numeric":
                type_check = (
                    f" WHEN TRIM({s_raw}) NOT IN {_sql_str_list(cfg.null_tokens)} AND TRY_CAST({s_raw} AS DOUBLE) IS NULL "
                    f"THEN 'TYPE_MISMATCH_SOURCE'"
                    f" WHEN TRIM({t_raw}) NOT IN {_sql_str_list(cfg.null_tokens)} AND TRY_CAST({t_raw} AS DOUBLE) IS NULL "
                    f"THEN 'TYPE_MISMATCH_TARGET'"
                )
            status_expr = (
                f"CASE WHEN {s_norm} IS NULL AND {t_norm} IS NULL THEN 'MATCH' "
                f"WHEN {s_norm} IS NULL AND {t_norm} IS NOT NULL THEN 'NULL_IN_SOURCE' "
                f"WHEN {s_norm} IS NOT NULL AND {t_norm} IS NULL THEN 'NULL_IN_TARGET'"
                f"{type_check}"
                f" WHEN {s_norm} = {t_norm} THEN 'MATCH' ELSE 'CHANGED' END"
            )
            union_parts.append(
                "SELECT s.__key AS matching_key, "
                f"'{f.target_column}' AS field_name, "
                f"CAST({s_raw} AS VARCHAR) AS source_value, "
                f"CAST({t_raw} AS VARCHAR) AS target_value, "
                f"{status_expr} AS status "
                "FROM src_unique s JOIN tgt_unique t ON s.__key = t.__key"
            )

        full_union = " UNION ALL ".join(union_parts)
        con.execute(
            f"COPY (SELECT * FROM ({full_union}) WHERE status != 'MATCH') "
            f"TO '{field_diff_path}' (FORMAT PARQUET)"
        )
        con.execute(
            f"COPY (SELECT matching_key, COUNT(*) AS differing_fields, "
            f"STRING_AGG(field_name, ', ') AS fields_changed "
            f"FROM read_parquet('{field_diff_path}') GROUP BY matching_key) "
            f"TO '{changed_keys_path}' (FORMAT PARQUET)"
        )
        changed_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{changed_keys_path}')").fetchone()[0]
    else:
        con.execute(f"COPY (SELECT NULL AS matching_key, NULL AS field_name, NULL AS source_value, "
                     f"NULL AS target_value, NULL AS status WHERE FALSE) TO '{field_diff_path}' (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT NULL AS matching_key, NULL AS differing_fields, NULL AS fields_changed "
                     f"WHERE FALSE) TO '{changed_keys_path}' (FORMAT PARQUET)")

    report(90, "Finalizing summary")
    con.close()

    summary = {
        "source_rows": source_rows,
        "target_rows": target_rows,
        "unique_source_customers": unique_source,
        "unique_target_customers": unique_target,
        "matched": matched_count,
        "missing": missing_count,
        "extra": extra_count,
        "changed": changed_count,
        "duplicates_in_source": dup_source_count,
        "duplicates_in_target": dup_target_count,
        "source_rows_with_null_key": source_null_keys,
        "target_rows_with_null_key": target_null_keys,
    }

    files = {
        "missing": missing_path,
        "extra": extra_path,
        "field_diffs": field_diff_path,
        "changed_keys": changed_keys_path,
        "duplicates_source": dup_source_path,
        "duplicates_target": dup_target_path,
    }

    report(100, "Completed")
    return RunResult(summary=summary, files=files)
