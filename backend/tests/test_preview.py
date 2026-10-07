import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app

client = TestClient(app)

CSV = b"a,when,b\n1,2024-01-05,x\n2,2024-01-06,y\n3,2024-01-07,z\n"


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def dataset_id():
    return client.post("/upload", files={"file": ("d.csv", CSV)}).json()["dataset_id"]


def test_preview_returns_the_requested_rows(dataset_id):
    body = client.get(f"/datasets/{dataset_id}/preview?rows=2").json()
    assert body["columns"] == ["a", "when", "b"]
    assert body["rows"][0] == [1, "2024-01-05", "x"]
    assert len(body["rows"]) == 2
    assert body["total_rows"] == 3


def test_preview_default_returns_all_small_rows(dataset_id):
    assert len(client.get(f"/datasets/{dataset_id}/preview").json()["rows"]) == 3


def test_preview_row_limits(dataset_id):
    assert client.get(f"/datasets/{dataset_id}/preview?rows=0").status_code == 422
    assert client.get(f"/datasets/{dataset_id}/preview?rows=101").status_code == 422


def test_preview_unknown_dataset():
    assert client.get(f"/datasets/{'0' * 32}/preview").status_code == 404