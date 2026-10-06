import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.analysis import build_eda
from agents.kpis import build_kpis
from config import settings
from main import app

client = TestClient(app)

SAMPLE_CSV = b'''Order ID,Order Date,City,Product,Price,Quantity
1001,05/01/2024,Hyderabad,Laptop,"55,000",2
1002,18/01/2024,hyderabad,Mouse,700,5
1003,22/01/2024,Vizag,Keyboard,"1,500",3
1004,03/02/2024,VIZAG ,Laptop,"55,000",1
1005,14/02/2024,Chennai,Monitor,"12,000",
1006,27/02/2024,Chennai,Mouse,700,10
1007,09/03/2024,Hyderabad,Laptop,"55,000",2
1008,21/03/2024,-,Keyboard,"1,500",4
1009,30/03/2024,Vizag,Monitor,"12,000",2
1010,11/04/2024,Hyderabad,Mouse,N/A,6
1011,19/04/2024,Chennai,Laptop,"5,50,000",1
1012,25/04/2024,hyderabad,Keyboard,"1,500",3
1012,25/04/2024,hyderabad,Keyboard,"1,500",3
'''


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def sales_df():
    i = np.arange(90)
    return pd.DataFrame(
        {
            "order_date": pd.date_range("2024-01-01", periods=90, freq="D"),
            "product": ["A", "B", "C"] * 30,
            "region": ["North", "South"] * 45,
            "units": [1, 2, 3] * 30,
            "revenue": 100 * ((i % 3) + 1),
        }
    )


@pytest.fixture
def hr_df():
    i = np.arange(40)
    department = np.array(["Engineering"] * 15 + ["Sales"] * 15 + ["HR"] * 10)
    base = np.where(department == "Engineering", 90000, np.where(department == "Sales", 60000, 50000))
    return pd.DataFrame(
        {
            "employee_id": i + 1,
            "department": department,
            "salary": base + (i % 5) * 1000,
            "age": 25 + (i % 20),
            "joining_date": pd.date_range("2022-01-03", periods=40, freq="W-MON"),
        }
    )


def make(df):
    return build_kpis(df, build_eda(df))


def card(result, kpi_id):
    return next((c for c in result["cards"] if c["id"] == kpi_id), None)


def test_sales_dataset_kpis(sales_df):
    result = make(sales_df)
    assert card(result, "total-records")["value"] == 90
    assert card(result, "total-revenue")["value"] == 18000
    assert card(result, "total-revenue")["format"] == "money"
    assert card(result, "average-revenue")["value"] == 200
    assert card(result, "total-units")["value"] == 180
    top = card(result, "top-product")
    assert top["value"] == "C"
    assert "50.0%" in top["subtitle"]
    assert result["roles"]["primary_measure"] == "revenue"
    assert result["roles"]["secondary_measure"] == "units"


def test_sales_time_kpis(sales_df):
    result = make(sales_df)
    assert card(result, "best-period") is not None
    latest = card(result, "latest-vs-previous")
    assert latest is not None and "week" in latest["label"]
    assert latest["direction"] in {"up", "down", "flat"}
    assert card(result, "period-covered")["value"] == "2024-01-01 to 2024-03-30"


def test_hr_dataset_adapts(hr_df):
    result = make(hr_df)
    assert result["roles"]["primary_measure"] == "salary"
    assert card(result, "total-salary")["value"] == 2830000
    assert card(result, "average-salary")["value"] == 70750
    top = card(result, "top-department")
    assert top["value"] == "Engineering"
    assert "48.8%" in top["subtitle"]
    assert card(result, "total-units") is None  # no sales-style KPIs are invented


def test_generic_dataset_uses_plain_averages():
    x = np.linspace(0, 10, 40) ** 2
    df = pd.DataFrame({"x1": x, "kind": ["a", "b"] * 20})
    result = make(df)
    assert "first numeric column" in result["roles"]["primary_basis"]
    assert result["roles"]["aggregation"] == "mean"
    assert card(result, "total-x1") is None
    assert card(result, "average-x1") is not None
    top = card(result, "top-kind")
    assert top["value"] == "b"
    assert "Highest average" in top["subtitle"]
    assert not any(c["category"] == "time" for c in result["cards"])


def test_text_only_dataset():
    result = make(pd.DataFrame({"city": ["a", "b", "a", "c"]}))
    assert result["roles"]["primary_measure"] is None
    assert card(result, "top-city")["value"] == "a"
    assert card(result, "total-records")["value"] == 4


def test_skewed_measure_mentions_median():
    df = pd.DataFrame({"v": [1, 2, 2, 3, 3, 3, 4, 4, 5, 200] * 5})
    avg = card(make(df), "average-v")
    assert "Median" in avg["subtitle"]
    assert "extreme" in avg["subtitle"]


def test_cards_are_complete_unique_and_json_safe(sales_df):
    result = make(sales_df)
    json.dumps(result)
    ids = [c["id"] for c in result["cards"]]
    assert len(ids) == len(set(ids))
    assert len(ids) <= 12
    for c in result["cards"]:
        assert {"id", "label", "value", "display", "format", "subtitle", "category"} <= set(c)


def test_kpis_endpoint():
    dataset_id = client.post("/upload", files={"file": ("s.csv", SAMPLE_CSV)}).json()["dataset_id"]
    r = client.get(f"/datasets/{dataset_id}/kpis")
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert kpis["roles"]["primary_measure"] == "price"
    assert kpis["roles"]["aggregation"] == "mean"  # prices are averaged, never summed
    cards = {c["id"]: c for c in kpis["cards"]}
    assert cards["total-records"]["value"] == 12
    assert "average-price" in cards
    assert "total-quantity" in cards


def test_kpis_unknown_dataset():
    assert client.get(f"/datasets/{'0' * 32}/kpis").status_code == 404