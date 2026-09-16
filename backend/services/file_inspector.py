"""
Inspects an uploaded CSV without ever loading it fully into Python memory.

Uses:
- `chardet` (sampled) for encoding detection
- csv.Sniffer (sampled) for delimiter detection
- DuckDB's `read_csv_auto` for row/column counts, dtype inference and a
  bounded-row preview. DuckDB streams the file rather than materialising
  it, so this is safe for multi-million-row files.

Every CSV that is successfully inspected is also written once to Parquet
(via DuckDB's COPY) so that every subsequent query (preview, validation,
export) reads compressed columnar data instead of re-parsing the CSV.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Optional

import chardet
import duckdb


class FileInspectionError(Exception):
    """Raised with a user-friendly message when a CSV cannot be inspected."""


@dataclass
class InspectionResult:
    row_count: int
    column_count: int
    encoding: str
    delimiter: str
    has_bom: bool
    columns: dict  # {name: duckdb_dtype}
    warnings: list = field(default_factory=list)
    preview_rows: list = field(default_factory=list)  # list of dicts
    parquet_path: Optional[str] = None


def read_preview_rows(path: str, rows: int, *, delimiter: str = ",") -> list[dict]:
    """Cheaply fetches a bounded row preview.

    Unlike `inspect_csv`, this never recomputes the schema or row count —
    callers already have those from the initial inspection. Reads from a
    Parquet copy when available (fast, columnar); falls back to a bounded
    CSV scan via DuckDB's `read_csv_auto` otherwise. Either way DuckDB's
    `LIMIT` is pushed down, so this touches a small slice of the file
    regardless of how many million rows it contains.
    """
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    try:
        if path.endswith(".parquet"):
            source_expr = f"read_parquet('{path}')"
        else:
            source_expr = f"read_csv_auto('{path}', delim='{delimiter}', header=True, ignore_errors=True, all_varchar=True)"
        df = con.execute(f"SELECT * FROM {source_expr} LIMIT {int(rows)}").fetchdf()
        return df.astype(object).where(df.notnull(), None).to_dict(orient="records")
    finally:
        con.close()


def _detect_encoding(path: str, sample_bytes: int = 1_000_000) -> tuple[str, bool]:
    with open(path, "rb") as f:
        raw = f.read(sample_bytes)
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    if has_bom:
        return "utf-8-sig", True
    detected = chardet.detect(raw)
    enc = (detected.get("encoding") or "utf-8").lower()
    # Normalise common aliases DuckDB understands well.
    if enc in ("ascii",):
        enc = "utf-8"
    return enc, has_bom


def _detect_delimiter(path: str, encoding: str, sample_bytes: int = 65536) -> str:
    try:
        with open(path, "r", encoding=encoding, errors="replace") as f:
            sample = f.read(sample_bytes)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def inspect_csv(path: str, parquet_out_path: Optional[str] = None, preview_rows: int = 50) -> InspectionResult:
    if not os.path.exists(path):
        raise FileInspectionError(f"The uploaded file could not be found on disk: {os.path.basename(path)}")
    if os.path.getsize(path) == 0:
        raise FileInspectionError(
            f"'{os.path.basename(path)}' is empty. Please upload a CSV file that contains at least a header row."
        )

    warnings: list[str] = []

    encoding, has_bom = _detect_encoding(path)
    delimiter = _detect_delimiter(path, "utf-8" if has_bom else encoding)

    con = duckdb.connect()
    con.execute("PRAGMA threads=4")

    # Two read strategies over the same file:
    #  - `typed_expr` (all_varchar=False) is used ONLY to infer a display data
    #    type per column (shown in the UI / used for mapping-type guesses).
    #  - `read_csv_expr` (all_varchar=True) is the one actually materialised
    #    (row count, preview, and the persisted Parquet copy). DuckDB's CSV
    #    reader silently drops any row that fails to cast into an inferred
    #    typed column even with ignore_errors=True — e.g. one stray
    #    non-numeric value in an otherwise-numeric column loses that whole
    #    row, with no error and no warning. Reading everything as VARCHAR
    #    avoids that cast entirely, so no row is ever silently discarded for
    #    this reason; the validation engine already CASTs every column to
    #    VARCHAR itself before normalising/comparing, so this loses nothing
    #    downstream.
    typed_expr = (
        f"read_csv_auto('{path}', delim='{delimiter}', header=True, "
        f"sample_size=200000, ignore_errors=True, all_varchar=False)"
    )
    read_csv_expr = (
        f"read_csv_auto('{path}', delim='{delimiter}', header=True, "
        f"sample_size=200000, ignore_errors=True, all_varchar=True)"
    )

    try:
        schema_rows = con.execute(f"DESCRIBE SELECT * FROM {typed_expr}").fetchall()
    except duckdb.Error as e:
        raise FileInspectionError(
            f"'{os.path.basename(path)}' could not be parsed as CSV. "
            f"It may use an unusual delimiter or be corrupted. Detail: {e}"
        )

    if not schema_rows:
        raise FileInspectionError(f"No columns could be detected in '{os.path.basename(path)}'.")

    columns: dict[str, str] = {}
    seen = set()
    for col_name, col_type, *_ in schema_rows:
        final_name = col_name
        n = 1
        while final_name in seen:
            n += 1
            final_name = f"{col_name}_{n}"
            warnings.append(
                f"Duplicate column name '{col_name}' found — the extra occurrence was renamed to '{final_name}'."
            )
        seen.add(final_name)
        columns[final_name] = col_type

    try:
        row_count = con.execute(f"SELECT COUNT(*) FROM {read_csv_expr}").fetchone()[0]
    except duckdb.Error as e:
        raise FileInspectionError(f"Could not count rows in '{os.path.basename(path)}'. Detail: {e}")

    try:
        preview_df = con.execute(f"SELECT * FROM {read_csv_expr} LIMIT {int(preview_rows)}").fetchdf()
        preview = preview_df.astype(object).where(preview_df.notnull(), None).to_dict(orient="records")
    except duckdb.Error:
        preview = []
        warnings.append("A row preview could not be generated for this file.")

    parquet_path = None
    if parquet_out_path:
        try:
            os.makedirs(os.path.dirname(parquet_out_path), exist_ok=True)
            con.execute(f"COPY (SELECT * FROM {read_csv_expr}) TO '{parquet_out_path}' (FORMAT PARQUET)")
            parquet_path = parquet_out_path
        except duckdb.Error as e:
            warnings.append(f"Could not create an optimized copy of this file for fast querying: {e}")

    con.close()

    return InspectionResult(
        row_count=row_count,
        column_count=len(columns),
        encoding=encoding,
        delimiter=delimiter,
        has_bom=has_bom,
        columns=columns,
        warnings=warnings,
        preview_rows=preview,
        parquet_path=parquet_path,
    )
