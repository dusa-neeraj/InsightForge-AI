import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.cleaning import clean_data
from config import settings
from main import app
from utils.errors import DatasetError

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


def test_column_names_standardized_and_unique():
    df = pd.DataFrame({"Order Date (UTC)": [1, 2, 3], "Name": [4, 5, 6], "name ": [7, 8, 9]})
    cleaned, report = clean_data(df)
    assert list(cleaned.columns) == ["order_date_utc", "name", "name_2"]
    assert report["columns_renamed"]["Name"] == "name"


def test_placeholders_become_missing():
    df = pd.DataFrame({"city": ["Hyd", "-", "N/A", "Vizag", " "], "v": [1, 2, 3, 4, 5]})
    cleaned, report = clean_data(df)
    assert report["placeholders_to_missing"]["city"] == 3
    assert report["missing_before"]["city"] == 3
    assert cleaned["city"].isna().sum() == 0


def test_currency_text_converted_to_numeric():
    df = pd.DataFrame({"price": ["$1,200", "$800", "$1,500", "$900"]})
    cleaned, report = clean_data(df)
    assert pd.api.types.is_numeric_dtype(cleaned["price"])
    assert 1200 in cleaned["price"].values
    assert report["type_conversions"]["price"]["to"] == "numeric"


def test_leading_zero_ids_not_converted():
    df = pd.DataFrame({"zip": ["01234", "05678", "09012", "01111"]})
    cleaned, report = clean_data(df)
    assert "zip" not in report["type_conversions"]
    assert cleaned["zip"].iloc[0] == "01234"


def test_dates_detected_without_name_hint():
    df = pd.DataFrame({"joined_on": ["2024-01-01", "2024-02-01", "2024-03-01"]})
    cleaned, report = clean_data(df)
    assert pd.api.types.is_datetime64_any_dtype(cleaned["joined_on"])
    assert report["type_conversions"]["joined_on"]["to"] == "datetime"


def test_day_first_dates_detected():
    df = pd.DataFrame({"order_date": ["25/01/2024", "03/02/2024", "15/03/2024"]})
    cleaned, report = clean_data(df)
    assert report["type_conversions"]["order_date"]["day_first"] is True
    assert cleaned["order_date"].iloc[1].month == 2  # 03/02 is 3 February


def test_inconsistent_values_standardized():
    df = pd.DataFrame(
        {"city": ["Hyd", "Hyd", "hyd", "HYD ", "Vizag", "Vizag"], "n": [1, 2, 3, 4, 5, 6]}
    )
    cleaned, report = clean_data(df)
    assert set(cleaned["city"]) == {"Hyd", "Vizag"}
    assert report["values_standardized"]["city"]["cells_changed"] == 2


def test_empty_rows_and_columns_removed():
    df = pd.DataFrame({"a": [1, None, 3], "b": [None, None, None], "c": ["x", None, "z"]})
    cleaned, report = clean_data(df)
    assert cleaned.shape == (2, 2)
    assert report["empty_rows_removed"] == 1
    assert report["empty_columns_dropped"] == ["b"]


def test_high_missing_column_not_filled():
    df = pd.DataFrame({"id": range(10), "x": [1, 2, 3] + [None] * 7})
    cleaned, report = clean_data(df)
    assert cleaned["x"].isna().sum() == 7
    assert report["missing_skipped_high"]["x"] == 70.0


def test_outliers_flagged_not_removed():
    df = pd.DataFrame({"id": range(8), "v": [10, 11, 12, 11, 10, 12, 11, 1000]})
    cleaned, report = clean_data(df)
    assert len(cleaned) == 8
    assert report["outliers_flagged"] == {"v": 1}
    assert report["outlier_details"]["v"]["highest_outlier"] == 1000.0


def test_report_is_json_safe():
    df = pd.DataFrame(
        {
            "City Name": ["Hyd", "hyd", "-", "Vizag"],
            "Price": ["$1,200", "$800", "$900", "$100000"],
            "joined_on": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            "Score": [1.0, None, 3.0, 4.0],
        }
    )
    _, report = clean_data(df)
    json.dumps(report)  # fails if numpy types leak into the report


def test_all_empty_dataset_raises():
    with pytest.raises(DatasetError):
        clean_data(pd.DataFrame({"a": [None, None]}))


def test_quality_endpoint_describes_new_steps():
    csv = b'City,Price\nHyd,"$1,200"\nhyd,$800\nVizag,-\nVizag,$900\n'
    dataset_id = client.post("/upload", files={"file": ("d.csv", csv)}).json()["dataset_id"]
    quality = client.get(f"/datasets/{dataset_id}/quality").json()["quality"]
    types = {c["type"] for c in quality["changes"]}
    assert {"columns_renamed", "placeholders_to_missing", "type_converted",
            "values_standardized", "missing_filled"} <= types


def test_upload_of_blank_file_returns_422():
    r = client.post("/upload", files={"file": ("blank.csv", b"a,b\n,\n,\n")})
    assert r.status_code == 422
    assert "error" in r.json()