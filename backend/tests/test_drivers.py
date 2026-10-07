import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.periods import previous_period, resolve_period
from agents.query_executor import execute_plan
from agents.query_plan import PlanError, QueryPlan, validate_plan
from agents.why_planner import why_plan
from config import settings
from main import app
from services import llm_service

client = TestClient(app)

SCHEMA = {"date_columns": ["order_date"], "default_measure": "revenue",
          "aggregations": {"revenue": "sum"}}


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


def decline_df(reverse: bool = False) -> pd.DataFrame:
    """June to July: Laptop in the South drops the most."""
    values = {
        ("Laptop", "North"): (3000, 3000),
        ("Laptop", "South"): (3000, 1200),
        ("Mouse", "North"): (600, 600),
        ("Mouse", "South"): (600, 300),
    }
    june = ["2024-06-05", "2024-06-15", "2024-06-25"]
    july = ["2024-07-05", "2024-07-15", "2024-07-31"]
    rows = []
    for (product, region), (jun, jul) in values.items():
        if reverse:
            jun, jul = jul, jun
        for date in june:
            rows.append({"order_date": date, "product": product, "region": region, "revenue": jun // 3})
        for date in july:
            rows.append({"order_date": date, "product": product, "region": region, "revenue": jul // 3})
    df = pd.DataFrame(rows)
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def run(df, period="July", **extra):
    plan = QueryPlan(operation="change_drivers", measure="revenue", aggregation="sum",
                     period=period, **extra)
    return execute_plan(validate_plan(plan, df), df)


def upload(df) -> str:
    csv = df.to_csv(index=False).encode()
    return client.post("/upload", files={"file": ("sales.csv", csv)}).json()["dataset_id"]


def ask(dataset_id, question):
    r = client.post(f"/datasets/{dataset_id}/chat", json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- the analysis ----------

def test_drivers_explain_a_decline():
    result = run(decline_df())
    assert result["kind"] == "drivers"
    assert (result["previous_period"], result["target_period"]) == ("2024-06", "2024-07")
    assert result["previous_value"] == 7200 and result["target_value"] == 5100
    assert result["change"] == -2100 and result["change_pct"] == -29.2
    assert result["direction"] == "decrease"

    region, product = result["dimensions"]  # ranked by how much one group explains
    assert region["column"] == "region"
    assert region["contributors"][0] == {
        "group": "South", "previous": 3600, "current": 1500, "change": -2100, "share_pct": 100.0}
    assert product["column"] == "product"
    assert product["contributors"][0]["group"] == "Laptop"
    assert product["contributors"][0]["share_pct"] == 85.7
    assert result["chart"]["figure"]["data"][0]["type"] == "bar"


def test_drivers_for_an_increase():
    result = run(decline_df(reverse=True))
    assert result["direction"] == "increase"
    assert result["change"] == 2100 and result["change_pct"] == 41.2


def test_latest_period_with_month_grain():
    result = run(decline_df(), period="latest", time_grain="month")
    assert result["target_period"] == "2024-07"


def test_missing_previous_period_is_a_clear_error():
    with pytest.raises(PlanError, match="2024-05"):
        run(decline_df(), period="June")


def test_period_resolution():
    df = pd.DataFrame({"d": pd.to_datetime(["2023-06-10", "2023-07-10", "2024-06-10", "2024-07-10"])})
    assert resolve_period(df, "d", "july", None) == ("2024-07", "month")  # latest July
    assert resolve_period(df, "d", "July 2023", None) == ("2023-07", "month")
    assert resolve_period(df, "d", "2023-06", None) == ("2023-06", "month")
    assert resolve_period(df, "d", "2024-03-04", "week") == ("2024-03-04", "week")
    # the data ends mid-July, so "latest month" skips the unfinished month
    assert resolve_period(df, "d", "latest", "month") == ("2024-06", "month")
    with pytest.raises(PlanError, match="December"):
        resolve_period(df, "d", "december", None)
    with pytest.raises(PlanError):
        resolve_period(df, "d", "banana", None)


def test_previous_period_labels():
    assert previous_period("2024-01", "month") == "2023-12"
    assert previous_period("2024-03-01", "day") == "2024-02-29"
    assert previous_period("2024-03-04", "week") == "2024-02-26"


def test_averages_are_rejected():
    plan = QueryPlan(operation="change_drivers", measure="revenue", aggregation="mean", period="July")
    with pytest.raises(PlanError, match="totals"):
        validate_plan(plan, decline_df())


def test_incomplete_target_period_is_flagged():
    df = decline_df()
    df = df[df["order_date"] <= "2024-07-20"]
    result = run(df)
    assert result["target_partial"] is True
    assert any("not finished" in note for note in result["notes"])


def test_small_samples_are_flagged():
    df = pd.DataFrame({
        "order_date": pd.to_datetime(["2024-05-10", "2024-05-20", "2024-06-10", "2024-06-30"]),
        "region": ["N", "S", "N", "S"],
        "revenue": [100, 100, 50, 50],
    })
    result = run(df, period="June")
    assert result["direction"] == "decrease"
    assert any("only 2 rows" in note for note in result["notes"])


def test_drivers_result_is_json_safe():
    json.dumps(run(decline_df()))


# ---------- planning "why" questions ----------

def test_why_planner_parses_periods():
    plan = why_plan("why did revenue fall in july 2024?", SCHEMA, None)
    assert (plan.operation, plan.period, plan.time_grain) == ("change_drivers", "july 2024", "month")
    latest = why_plan("why did revenue drop last month", SCHEMA, None)
    assert (latest.period, latest.time_grain) == ("latest", "month")
    assert why_plan("why did revenue change in may", SCHEMA, "revenue").period == "may"
    assert why_plan("why? it may be due to price", SCHEMA, None).period == "latest"


def test_why_planner_refuses_unsuitable_data():
    averaged = {**SCHEMA, "default_measure": "price", "aggregations": {"price": "mean"}}
    plan = why_plan("why did price drop?", averaged, None)
    assert plan.operation == "unsupported" and "average" in plan.reason
    no_dates = {**SCHEMA, "date_columns": []}
    assert "date column" in why_plan("why did revenue drop?", no_dates, None).reason


# ---------- through the chat API ----------

@pytest.fixture
def dataset_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    return upload(decline_df())


def test_why_question_through_the_api(dataset_id):
    body = ask(dataset_id, "Why did revenue drop in July?")
    assert body["status"] == "ok"
    assert body["plan"]["operation"] == "change_drivers"
    assert body["result"]["kind"] == "drivers"
    assert "fell" in body["answer"] and "South" in body["answer"]
    assert "cannot prove why" in body["answer"]
    assert len(body["method"]) >= 2


def test_why_question_with_missing_month(dataset_id):
    body = ask(dataset_id, "Why did revenue drop in December?")
    assert body["status"] == "error"
    assert "December" in body["answer"]


def test_ai_planned_driver_question(dataset_id, monkeypatch):
    plan = {"operation": "change_drivers", "measure": "revenue", "aggregation": "sum",
            "group_by": [], "filters": [], "sort": "desc", "limit": None, "date_column": None,
            "time_grain": None, "period": "July", "reason": None}
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", lambda system, user, **kw: plan)
    body = ask(dataset_id, "What caused the July revenue change?")
    assert body["source"] == "ai"
    assert body["result"]["kind"] == "drivers"
    assert body["result"]["change"] == -2100