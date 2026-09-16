"""
End-to-end API tests: project -> upload -> mapping -> run -> results -> export.

Run with:  pytest tests/test_api.py -v
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    # Reimport with fresh env vars picked up
    for mod in list(sys.modules):
        if mod in ("main", "database", "utils.storage_paths", "api.files", "api.projects"):
            del sys.modules[mod]
    from main import app  # noqa
    with TestClient(app) as c:
        yield c


def _wait_for_run(client, project_id, run_id, timeout=30):
    for _ in range(timeout * 5):
        r = client.get(f"/api/projects/{project_id}/runs/{run_id}")
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.2)
    raise TimeoutError("Validation run did not finish in time")


def test_full_workflow(client):
    r = client.post("/api/projects", json={"name": "API Test Project"})
    assert r.status_code == 200
    project_id = r.json()["id"]

    src_csv = b"OBCustomerNo,FirstName\n1001,Rahul\n1002,Anita\n1003,Suresh\n"
    tgt_csv = b"custid,first_name\n1001,Rahul\n1002,Anita\n1004,John\n"

    r = client.post(f"/api/projects/{project_id}/files", files={"file": ("src.csv", src_csv, "text/csv")})
    assert r.status_code == 200
    src_id = r.json()["id"]
    assert r.json()["row_count"] == 3

    r = client.post(f"/api/projects/{project_id}/files", files={"file": ("tgt.csv", tgt_csv, "text/csv")})
    tgt_id = r.json()["id"]

    mapping_payload = {
        "name": "Test Mapping",
        "source_file_id": src_id,
        "target_file_id": tgt_id,
        "column_mappings": [
            {"source_columns": ["OBCustomerNo"], "target_column": "custid", "data_type": "numeric", "is_matching_key": True, "compare_in_validation": False},
            {"source_columns": ["FirstName"], "target_column": "first_name", "data_type": "string"},
        ],
    }
    r = client.post(f"/api/projects/{project_id}/mappings", json=mapping_payload)
    assert r.status_code == 200
    mapping_id = r.json()["id"]

    r = client.post(f"/api/projects/{project_id}/runs", json={"mapping_id": mapping_id})
    assert r.status_code == 200
    run_id = r.json()["id"]

    data = _wait_for_run(client, project_id, run_id)
    assert data["status"] == "completed"
    assert data["summary_json"]["missing"] == 1
    assert data["summary_json"]["extra"] == 1
    assert data["summary_json"]["matched"] == 2

    r = client.get(f"/api/projects/{project_id}/runs/{run_id}/results/missing")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = client.get(f"/api/projects/{project_id}/runs/{run_id}/export/excel")
    assert r.status_code == 200
    assert len(r.content) > 0


def test_missing_column_gives_friendly_error(client):
    r = client.post("/api/projects", json={"name": "Error Test"})
    project_id = r.json()["id"]
    r = client.post(f"/api/projects/{project_id}/files", files={"file": ("src.csv", b"a,b\n1,2\n", "text/csv")})
    src_id = r.json()["id"]
    r = client.post(f"/api/projects/{project_id}/files", files={"file": ("tgt.csv", b"x,y\n1,2\n", "text/csv")})
    tgt_id = r.json()["id"]

    payload = {
        "name": "Bad Mapping",
        "source_file_id": src_id,
        "target_file_id": tgt_id,
        "column_mappings": [
            {"source_columns": ["does_not_exist"], "target_column": "x", "is_matching_key": True},
        ],
    }
    r = client.post(f"/api/projects/{project_id}/mappings", json=payload)
    assert r.status_code == 422
    assert "does_not_exist" in r.json()["detail"]["message"]


def test_project_delete_cleans_up(client):
    r = client.post("/api/projects", json={"name": "To Delete"})
    project_id = r.json()["id"]
    client.post(f"/api/projects/{project_id}/files", files={"file": ("a.csv", b"a\n1\n", "text/csv")})
    r = client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 200
    r = client.get(f"/api/projects/{project_id}")
    assert r.status_code == 404
