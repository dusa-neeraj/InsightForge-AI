import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.profiling import profile_dataframe
from config import settings
from main import app

client = TestClient(app)

CSV = b"Name,Age,City\nA,25,Hyd\nB,30,Hyd\nB,30,Hyd\nC,,Vizag\n"


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "price": [10.0, 20.0, 30.0, 40.0, 1000.0, None],
            "city": ["A", "A", "B", None, "A", "B"],
            "order_date": pd.to_datetime(
                ["2024-01-01", "2024-01-15", "2024-02-01",
                 "2024-02-15", "2024-03-01", "2024-03-15"]
            ),
        }
    )


def col(profile, name):
    return next(c for c in profile["columns"] if c["name"] == name)


def upload(name: str, content: bytes) -> str:
    return client.post("/upload", files={"file": (name, content)}).json()["dataset_id"]


# ---------- unit tests ----------

def test_overview_counts(sample_df):
    df = pd.concat([sample_df, sample_df.iloc[[0]]])
    overview = profile_dataframe(df)["overview"]
    assert overview["rows"] == 7
    assert overview["columns"] == 3
    assert overview["duplicate_rows"] == 1


def test_missing_values(sample_df):
    profile = profile_dataframe(sample_df)
    assert col(profile, "price")["missing"] == 1
    assert col(profile, "price")["missing_pct"] == 16.67
    assert profile["overview"]["missing_cells"] == 2
    assert profile["overview"]["complete_rows"] == 4


def test_column_kinds(sample_df):
    types = profile_dataframe(sample_df)["column_types"]
    assert types["numeric"] == ["price"]
    assert types["categorical"] == ["city"]
    assert types["date"] == ["order_date"]


def test_numeric_stats_and_outliers(sample_df):
    price = col(profile_dataframe(sample_df), "price")
    assert price["min"] == 10
    assert price["max"] == 1000
    assert price["median"] == 30
    assert price["mean"] == 220
    assert price["quantiles"]["p25"] == 20
    assert price["quantiles"]["p75"] == 40
    assert price["outlier_count"] == 1


def test_categorical_top_values(sample_df):
    city = col(profile_dataframe(sample_df), "city")
    assert city["unique"] == 2
    assert city["top_values"][0] == {"value": "A", "count": 3, "pct": 60.0}


def test_date_stats(sample_df):
    date = col(profile_dataframe(sample_df), "order_date")
    assert date["min"].startswith("2024-01-01")
    assert date["span_days"] == 74


def test_likely_id():
    df = pd.DataFrame({"id": range(100), "value": [1.5] * 100})
    assert profile_dataframe(df)["column_types"]["likely_id"] == ["id"]


def test_all_missing_column_is_json_safe():
    df = pd.DataFrame({"x": [np.nan, np.nan], "y": [1, 2]})
    profile = profile_dataframe(df)
    json.dumps(profile)  # fails if numpy types or NaN leak through
    assert col(profile, "x")["missing_pct"] == 100.0


# ---------- endpoint tests ----------

def test_profile_clean():
    dataset_id = upload("data.csv", CSV)
    r = client.get(f"/datasets/{dataset_id}/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "clean"
    assert body["profile"]["overview"]["rows"] == 3
    assert body["profile"]["overview"]["duplicate_rows"] == 0


def test_profile_raw_has_duplicates():
    dataset_id = upload("data.csv", CSV)
    profile = client.get(f"/datasets/{dataset_id}/profile?version=raw").json()["profile"]
    assert profile["overview"]["rows"] == 4
    assert profile["overview"]["duplicate_rows"] == 1
    assert col(profile, "Age")["missing"] == 1


def test_dates_restored_from_csv():
    csv = b"order_date,amount\n2024-01-01,10\n2024-01-02,20\n2024-01-03,30\n"
    dataset_id = upload("sales.csv", csv)
    profile = client.get(f"/datasets/{dataset_id}/profile").json()["profile"]
    assert col(profile, "order_date")["kind"] == "date"


def test_unknown_dataset():
    r = client.get(f"/datasets/{'0' * 32}/profile")
    assert r.status_code == 404
    assert "error" in r.json()


def test_invalid_dataset_id():
    assert client.get("/datasets/abc/profile").status_code == 400