import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app

client = TestClient(app)

CSV = b"Name,Age,City\nA,25,Hyd\nB,30,Hyd\nB,30,Hyd\nC,,Vizag\n"


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


def post(name: str, content: bytes):
    return client.post("/upload", files={"file": (name, content)})


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_csv_success():
    r = post("data.csv", CSV)
    assert r.status_code == 200
    body = r.json()
    assert len(body["dataset_id"]) == 32
    assert body["report"]["duplicates_removed"] == 1
    assert body["report"]["rows_after"] == 3


def test_column_names_standardized():
    body = post("data.csv", CSV).json()
    assert "name" in body["preview"][0]


def test_missing_values_filled():
    body = post("data.csv", CSV).json()
    assert body["report"]["missing_before"] == {"age": 1}


def test_upload_xlsx_success():
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(buf, index=False)
    r = post("data.xlsx", buf.getvalue())
    assert r.status_code == 200


def test_unsupported_type():
    r = post("notes.txt", b"hello")
    assert r.status_code == 400
    assert "error" in r.json()


def test_empty_file():
    assert post("empty.csv", b"").status_code == 400


def test_corrupt_excel():
    assert post("bad.xlsx", b"this is not excel").status_code == 400


def test_file_too_large(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = b"a,b\n" + b"1,2\n" * 600_000
    assert post("big.csv", big).status_code == 413


def test_no_server_path_leak(tmp_path):
    r = post("data.csv", CSV)
    assert str(tmp_path) not in r.text