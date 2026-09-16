"""
Engine-level tests covering the scenarios called out in the spec:
exact matching, missing/extra ids, duplicates, case/whitespace, nulls,
numeric & date normalization, composite keys, and field comparison.

Run with:  pytest tests/test_engine.py -v
"""
import os
import sys
import shutil

import duckdb
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from validators.engine import EngineConfig, FieldMapping, run_validation, EngineError  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_tmp_engine_tests")


def _make_parquet(rows_csv: str, path: str):
    csv_path = path.replace(".parquet", ".csv")
    with open(csv_path, "w") as f:
        f.write(rows_csv)
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_csv_auto('{csv_path}')) TO '{path}' (FORMAT PARQUET)")
    con.close()


@pytest.fixture(autouse=True)
def clean_tmp():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    yield
    shutil.rmtree(TMP, ignore_errors=True)


def _cfg(**overrides):
    fields = [
        FieldMapping(source_columns=["OBCustomerNo"], target_column="custid", data_type="numeric", is_matching_key=True, compare_in_validation=False),
        FieldMapping(source_columns=["FirstName"], target_column="first_name", data_type="string"),
    ]
    return EngineConfig(fields=fields, **overrides)


def test_exact_match_missing_extra():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n1001,Rahul\n1002,Anita\n1003,Suresh\n", src)
    _make_parquet("custid,first_name\n1001,Rahul\n1002,Anita\n1004,John\n", tgt)

    result = run_validation(src, tgt, _cfg(), os.path.join(TMP, "out1"))
    assert result.summary["source_rows"] == 3
    assert result.summary["target_rows"] == 3
    assert result.summary["matched"] == 2
    assert result.summary["missing"] == 1
    assert result.summary["extra"] == 1


def test_duplicate_detection():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n1001,Rahul\n1001,Rahul\n1002,Anita\n", src)
    _make_parquet("custid,first_name\n1001,Rahul\n1002,Anita\n1002,Anita\n", tgt)

    result = run_validation(src, tgt, _cfg(), os.path.join(TMP, "out2"))
    assert result.summary["duplicates_in_source"] == 1
    assert result.summary["duplicates_in_target"] == 1


def test_case_and_whitespace_normalization():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n1001, rahul \n", src)
    _make_parquet("custid,first_name\n1001,RAHUL\n", tgt)

    result = run_validation(src, tgt, _cfg(trim=True, case_insensitive=True), os.path.join(TMP, "out3"))
    assert result.summary["changed"] == 0  # normalized values should match, no CHANGED flagged


def test_null_representation_handling():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n1001,N/A\n1002,Anita\n", src)
    _make_parquet("custid,first_name\n1001,\n1002,Anita\n", tgt)

    result = run_validation(src, tgt, _cfg(), os.path.join(TMP, "out4"))
    con = duckdb.connect()
    diffs = con.execute(f"SELECT * FROM read_parquet('{result.files['field_diffs']}')").fetchdf()
    con.close()
    # 1001: both sides normalize to NULL -> should be treated as MATCH (no diff row)
    assert diffs[diffs["matching_key"] == "1001"].empty


def test_numeric_normalization_leading_zeros():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n001234,Rahul\n", src)
    _make_parquet("custid,first_name\n1234,Rahul\n", tgt)

    result = run_validation(src, tgt, _cfg(numeric_normalize=True), os.path.join(TMP, "out5"))
    assert result.summary["matched"] == 1
    assert result.summary["missing"] == 0
    assert result.summary["extra"] == 0


def test_date_normalization():
    fields = [
        FieldMapping(source_columns=["id"], target_column="id", data_type="numeric", is_matching_key=True, compare_in_validation=False),
        FieldMapping(source_columns=["dob"], target_column="dob", data_type="date"),
    ]
    cfg = EngineConfig(fields=fields, date_normalize=True)
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("id,dob\n1,01/09/2026\n", src)
    _make_parquet("id,dob\n1,2026-09-01\n", tgt)

    result = run_validation(src, tgt, cfg, os.path.join(TMP, "out6"))
    assert result.summary["changed"] == 0


def test_composite_key():
    fields = [
        FieldMapping(source_columns=["FirstName"], target_column="first_name", data_type="string", is_matching_key=True, compare_in_validation=False),
        FieldMapping(source_columns=["LastName"], target_column="last_name", data_type="string", is_matching_key=True, compare_in_validation=False),
        FieldMapping(source_columns=["Email"], target_column="email", data_type="string"),
    ]
    cfg = EngineConfig(fields=fields)
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("FirstName,LastName,Email\nRahul,Sharma,a@x.com\nRahul,Verma,b@x.com\n", src)
    _make_parquet("first_name,last_name,email\nRahul,Sharma,a@x.com\nRahul,Iyer,c@x.com\n", tgt)

    result = run_validation(src, tgt, cfg, os.path.join(TMP, "out7"))
    assert result.summary["matched"] == 1  # Rahul Sharma only
    assert result.summary["missing"] == 1  # Rahul Verma
    assert result.summary["extra"] == 1  # Rahul Iyer


def test_field_level_comparison_changed():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n1001,Rahul\n", src)
    _make_parquet("custid,first_name\n1001,Rakesh\n", tgt)

    result = run_validation(src, tgt, _cfg(), os.path.join(TMP, "out8"))
    assert result.summary["changed"] == 1


def test_no_matching_key_raises():
    fields = [FieldMapping(source_columns=["a"], target_column="a", is_matching_key=False)]
    cfg = EngineConfig(fields=fields)
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("a\n1\n", src)
    _make_parquet("a\n1\n", tgt)
    with pytest.raises(EngineError):
        run_validation(src, tgt, cfg, os.path.join(TMP, "out9"))


def test_blank_key_rows_excluded():
    src = os.path.join(TMP, "src.parquet")
    tgt = os.path.join(TMP, "tgt.parquet")
    _make_parquet("OBCustomerNo,FirstName\n,Blank\n1001,Rahul\n", src)
    _make_parquet("custid,first_name\n1001,Rahul\n", tgt)

    result = run_validation(src, tgt, _cfg(), os.path.join(TMP, "out10"))
    assert result.summary["source_rows_with_null_key"] == 1
    assert result.summary["matched"] == 1
