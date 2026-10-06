import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.analysis import build_eda
from agents.profiling import profile_dataframe
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
    n = 120
    i = np.arange(n)
    region = np.where(i % 2 == 0, "North", "South")
    revenue = 1000 + 10 * i + np.where(region == "North", 500, 0)
    return pd.DataFrame(
        {
            "order_date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "region": region,
            "units": (i % 7) + 1,
            "revenue": revenue,
            "cost": revenue * 0.6,
        }
    )


def test_numeric_summary_shape_and_histogram():
    df = pd.DataFrame({"v": [1, 2, 2, 3, 3, 3, 4, 4, 5, 200] * 5})
    col = build_eda(df)["numeric"][0]
    assert col["shape"] == "highly right-skewed"
    assert sum(col["histogram"]["counts"]) == 50
    assert len(col["histogram"]["edges"]) == 11


def test_identifier_columns_excluded():
    df = pd.DataFrame(
        {"order_id": range(1, 13), "amount": [5.5, 7.1, 6.3, 9.9, 4.2, 8.8, 5.1, 6.6, 7.7, 3.9, 8.1, 6.0]}
    )
    eda = build_eda(df)
    assert {"name": "order_id", "reason": "identifier"} in eda["excluded_columns"]
    assert [c["name"] for c in eda["numeric"]] == ["amount"]


def test_salary_like_integers_not_flagged_as_identifier():
    df = pd.DataFrame({"salary": [30000 + i * 137 for i in range(30)]})
    assert profile_dataframe(df)["column_types"]["likely_id"] == []


def test_identifier_detected_by_name():
    df = pd.DataFrame({"customer_id": [5, 9, 12, 40, 41, 77, 90, 101, 150, 200]})
    assert profile_dataframe(df)["column_types"]["likely_id"] == ["customer_id"]


def test_strong_correlation_found():
    x = np.linspace(0, 10, 30)
    pair = build_eda(pd.DataFrame({"x": x, "y": 3 * x + 1}))["correlations"]["strong_pairs"][0]
    assert pair["strength"] == "very strong"
    assert pair["direction"] == "positive"
    assert pair["r"] == 1.0


def test_categorical_summary_and_dominant():
    df = pd.DataFrame({"city": ["Hyd"] * 7 + ["Vizag"] * 3})
    col = build_eda(df)["categorical"][0]
    assert col["top_values"][0] == {"value": "Hyd", "count": 7, "pct": 70.0}
    assert col["dominant"] is True


def test_category_effect_detected(sales_df):
    effects = build_eda(sales_df)["category_effects"]
    revenue = next(e for e in effects if e["measure"] == "revenue")
    assert revenue["category_column"] == "region"
    assert revenue["best_group"] == "North"
    assert revenue["eta_squared"] >= 0.1
    assert not any(e["measure"] == "units" for e in effects)


def test_time_trend_increasing_and_flat(sales_df):
    trend = build_eda(sales_df)["time_trends"][0]
    assert trend["grain"] == "week"
    assert trend["partial_last_period"] is True  # data ends on a Monday
    metrics = {m["name"]: m for m in trend["metrics"]}
    assert metrics["revenue"]["direction"] == "increasing"
    assert metrics["revenue"]["change_pct"] > 0
    assert metrics["units"]["direction"] == "flat"  # partial last week is ignored
    assert trend["weekday_pattern"]["peak_day"] == "Mon"


def test_relationships_generated(sales_df):
    types = {r["type"] for r in build_eda(sales_df)["relationships"]}
    assert {"correlation", "category_effect", "trend"} <= types


def test_eda_is_json_safe(sales_df):
    json.dumps(build_eda(sales_df))


def test_text_only_dataset_does_not_crash():
    eda = build_eda(pd.DataFrame({"a": ["x", "y", "x"]}))
    assert eda["numeric"] == []
    assert eda["time_trends"] == []
    assert eda["correlations"]["strong_pairs"] == []
    assert eda["overview"]["rows"] == 3


def test_eda_endpoint():
    dataset_id = client.post("/upload", files={"file": ("s.csv", SAMPLE_CSV)}).json()["dataset_id"]
    r = client.get(f"/datasets/{dataset_id}/eda")
    assert r.status_code == 200
    eda = r.json()["eda"]
    assert {"numeric", "categorical", "correlations", "time_trends", "relationships"} <= set(eda)
    assert "order_id" in {c["name"] for c in eda["excluded_columns"]}
    assert len(eda["time_trends"]) == 1


def test_eda_unknown_dataset():
    assert client.get(f"/datasets/{'0' * 32}/eda").status_code == 404