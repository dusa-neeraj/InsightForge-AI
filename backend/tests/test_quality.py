import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.profiling import profile_dataframe
from agents.quality import build_changes, find_issues, quality_score
from config import settings
from main import app

client = TestClient(app)

CSV = b"Name,Age,City\nA,25,Hyd\nB,30,Hyd\nB,30,Hyd\nC,,Vizag\n"


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


def upload(name: str, content: bytes) -> str:
    return client.post("/upload", files={"file": (name, content)}).json()["dataset_id"]


# ---------- unit tests ----------

def test_perfect_data_scores_100():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": ["x", "y", "x", "y", "x"]})
    result = quality_score(profile_dataframe(df))
    assert result["score"] == 100.0
    assert result["grade"] == "Excellent"


def test_missing_values_lower_the_score():
    df = pd.DataFrame({"a": [1, 2, 3, None]})
    result = quality_score(profile_dataframe(df))
    assert result["components"]["completeness"] == 75.0
    assert result["score"] == 87.5
    assert result["grade"] == "Good"


def test_build_changes_messages():
    df = pd.DataFrame({"age": [20.0, 25.0, 30.0], "salary": [1.0, 2.0, 3.0]})
    profile = profile_dataframe(df)
    report = {
        "duplicates_removed": 2,
        "missing_before": {"age": 3},
        "outliers_flagged": {"salary": 1},
    }
    changes = build_changes(report, profile, profile)
    assert [c["type"] for c in changes] == [
        "duplicates_removed", "missing_filled", "outliers_flagged",
    ]
    assert "median" in changes[1]["message"]


def test_no_changes_message():
    profile = profile_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
    changes = build_changes({}, profile, profile)
    assert changes[0]["type"] == "no_changes"


def test_find_issues():
    df = pd.DataFrame(
        {
            "price": [-5, 10, 12, 11, 10, 13, 12, 11],
            "const": ["x"] * 8,
            "empty": [None] * 8,
        }
    )
    issues = find_issues(profile_dataframe(df))
    types = {i["type"] for i in issues}
    assert {"negative_values", "constant_column", "empty_column", "small_dataset"} <= types
    assert issues[0]["type"] == "empty_column"  # high severity comes first


# ---------- endpoint tests ----------

def test_quality_endpoint():
    dataset_id = upload("data.csv", CSV)
    r = client.get(f"/datasets/{dataset_id}/quality")
    assert r.status_code == 200
    quality = r.json()["quality"]
    assert quality["before"]["duplicate_rows"] == 1
    assert quality["after"]["duplicate_rows"] == 0
    assert quality["before"]["score"] < quality["after"]["score"] == 100.0
    types = {c["type"] for c in quality["changes"]}
    assert {"duplicates_removed", "missing_filled"} <= types


def test_quality_works_without_saved_report():
    dataset_id = upload("data.csv", CSV)
    (settings.upload_dir / dataset_id / "cleaning_report.json").unlink()
    r = client.get(f"/datasets/{dataset_id}/quality")
    assert r.status_code == 200
    types = {c["type"] for c in r.json()["quality"]["changes"]}
    assert "duplicates_removed" in types


def test_quality_unknown_dataset():
    assert client.get(f"/datasets/{'0' * 32}/quality").status_code == 404