"""Builds server-side export files. Excel workbooks are streamed sheet by
sheet from DuckDB/Parquet using openpyxl's write-only mode so we never hold
a full dataset in memory twice."""
from __future__ import annotations

import os
import duckdb
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

MAX_ROWS_PER_SHEET_EXCEL = 200_000  # openpyxl practical ceiling for a single sheet in this MVP


def _write_sheet_from_parquet(wb: Workbook, sheet_name: str, parquet_path: str, limit: int = MAX_ROWS_PER_SHEET_EXCEL):
    ws = wb.create_sheet(title=sheet_name[:31])
    if not parquet_path or not os.path.exists(parquet_path):
        ws.append(["No data"])
        return
    con = duckdb.connect()
    total = con.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')").fetchone()[0]
    cols = [d[0] for d in con.execute(f"SELECT * FROM read_parquet('{parquet_path}') LIMIT 0").description]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = header_font
        cell.fill = header_fill
    for i, col in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(max(len(col) + 2, 12), 40)

    rel = con.execute(f"SELECT * FROM read_parquet('{parquet_path}') LIMIT {limit}").fetchall()
    for row in rel:
        ws.append(list(row))
    con.close()
    if total > limit:
        ws.append([])
        ws.append([f"... truncated. {total:,} total rows — export CSV for the complete dataset."])


def build_summary_sheet(wb: Workbook, summary: dict, project_name: str, mapping_name: str):
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Migration Validation Report"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Project", project_name])
    ws.append(["Mapping", mapping_name])
    ws.append([])
    ws.append(["Metric", "Value"])
    ws["A6"].font = Font(bold=True)
    ws["B6"].font = Font(bold=True)
    labels = {
        "source_rows": "Source Records",
        "target_rows": "Target Records",
        "unique_source_customers": "Unique Source Customers",
        "unique_target_customers": "Unique Target Customers",
        "matched": "Matched",
        "missing": "Missing in Target",
        "extra": "Extra in Target",
        "changed": "Changed (field-level differences)",
        "duplicates_in_source": "Duplicate Keys in Source",
        "duplicates_in_target": "Duplicate Keys in Target",
        "source_rows_with_null_key": "Source Rows with Blank/Null Key",
        "target_rows_with_null_key": "Target Rows with Blank/Null Key",
    }
    for key, label in labels.items():
        ws.append([label, summary.get(key, 0)])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 18


def export_full_report(
    out_path: str,
    project_name: str,
    mapping_name: str,
    summary: dict,
    result_files: dict,
) -> str:
    wb = Workbook()
    build_summary_sheet(wb, summary, project_name, mapping_name)
    _write_sheet_from_parquet(wb, "Missing Records", result_files.get("missing"))
    _write_sheet_from_parquet(wb, "Extra Records", result_files.get("extra"))
    _write_sheet_from_parquet(wb, "Changed Records", result_files.get("changed_keys"))
    _write_sheet_from_parquet(wb, "Field Differences", result_files.get("field_diffs"))
    _write_sheet_from_parquet(wb, "Duplicates - Source", result_files.get("duplicates_source"))
    _write_sheet_from_parquet(wb, "Duplicates - Target", result_files.get("duplicates_target"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    return out_path


def export_single_csv(parquet_path: str, out_path: str) -> str:
    con = duckdb.connect()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if parquet_path and os.path.exists(parquet_path):
        con.execute(f"COPY (SELECT * FROM read_parquet('{parquet_path}')) TO '{out_path}' (HEADER, DELIMITER ',')")
    else:
        with open(out_path, "w") as f:
            f.write("")
    con.close()
    return out_path
