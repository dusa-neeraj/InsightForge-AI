import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents import visualization
from agents.analysis import build_eda
from agents.visualization import build_charts
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


def make(df):
    return build_charts(df, build_eda(df))


def find(result, chart_type, *columns):
    return next(
        (c for c in result["charts"]
         if c["type"] == chart_type and set(c["columns"]) == set(columns)),
        None,
    )


def test_histogram_for_numeric(sales_df):
    chart = find(make(sales_df), "histogram", "revenue")
    assert chart is not None
    assert sum(chart["figure"]["data"][0]["y"]) == 120


def test_line_chart_marks_incomplete_period(sales_df):
    chart = find(make(sales_df), "line", "order_date", "revenue")
    assert chart is not None
    traces = chart["figure"]["data"]
    assert len(traces) == 2
    assert traces[1]["line"]["dash"] == "dot"
    assert "increasing" in chart["reason"]


def test_bar_for_category_effect(sales_df):
    chart = find(make(sales_df), "bar", "region", "revenue")
    assert chart is not None
    assert chart["section"] == "comparisons"
    assert chart["figure"]["data"][0]["x"][0] == "North"  # highest average first


def test_category_distribution_bar(sales_df):
    chart = find(make(sales_df), "bar", "region")
    assert chart is not None
    assert chart["section"] == "categories"
    assert len(chart["figure"]["data"][0]["x"]) == 2


def test_scatter_for_strong_correlation(sales_df):
    chart = find(make(sales_df), "scatter", "revenue", "cost")
    assert chart is not None
    assert len(chart["figure"]["data"]) == 2  # points + trend line
    assert "correlation" in chart["reason"]


def test_heatmap_needs_three_numeric_columns(sales_df):
    assert any(c["type"] == "heatmap" for c in make(sales_df)["charts"])
    x = np.linspace(0, 10, 30)
    two_numeric = make(pd.DataFrame({"x": x, "y": x ** 2}))
    assert not any(c["type"] == "heatmap" for c in two_numeric["charts"])


def test_box_plot_for_outliers():
    df = pd.DataFrame({"v": [10, 11, 12, 11, 10, 12, 11, 1000]})
    chart = find(make(df), "box", "v")
    assert chart is not None
    assert "outliers" in chart["reason"]


def test_every_chart_is_complete_and_ids_unique(sales_df):
    charts = make(sales_df)["charts"]
    assert charts
    for chart in charts:
        assert {"id", "type", "section", "title", "reason", "columns", "figure"} <= set(chart)
        assert chart["title"] and chart["reason"]
        assert {"data", "layout"} <= set(chart["figure"])
    ids = [c["id"] for c in charts]
    assert len(ids) == len(set(ids))


def test_charts_are_json_safe(sales_df):
    json.dumps(make(sales_df))


def test_text_only_dataset_does_not_crash():
    result = make(pd.DataFrame({"a": ["x", "y", "x"]}))
    assert {c["type"] for c in result["charts"]} <= {"bar"}


def test_failed_chart_is_skipped_not_fatal(sales_df, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(visualization, "_histogram", boom)
    result = make(sales_df)
    assert result["skipped"]
    assert not any(c["type"] == "histogram" for c in result["charts"])
    assert any(c["type"] == "line" for c in result["charts"])


def test_charts_endpoint():
    dataset_id = client.post("/upload", files={"file": ("s.csv", SAMPLE_CSV)}).json()["dataset_id"]
    r = client.get(f"/datasets/{dataset_id}/charts")
    assert r.status_code == 200
    body = r.json()
    assert body["charts"]
    assert {"histogram", "line", "bar"} <= set(body["counts"])


def test_charts_unknown_dataset():
    assert client.get(f"/datasets/{'0' * 32}/charts").status_code == 404