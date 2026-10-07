import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agents.query_plan import Filter, PlanError, QueryPlan, validate_plan
from config import settings
from main import app
from services import llm_service

client = TestClient(app)

CSV = b"""order_id,order_date,product,region,revenue,units
1,2024-01-05,Laptop,North,50000,1
2,2024-01-12,Mouse,North,700,5
3,2024-02-03,Laptop,South,50000,1
4,2024-02-14,Keyboard,South,1500,3
5,2024-03-09,Laptop,North,50000,1
6,2024-03-21,Mouse,South,900,4
7,2024-04-11,Keyboard,North,1500,2
8,2024-04-25,Laptop,South,50000,1
"""

TOP_PRODUCT_PLAN = {
    "operation": "aggregate", "measure": "revenue", "aggregation": "sum",
    "group_by": ["product"], "filters": [], "sort": "desc", "limit": 1,
    "date_column": None, "time_grain": None, "reason": None,
}


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def dataset_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    return client.post("/upload", files={"file": ("sales.csv", CSV)}).json()["dataset_id"]


@pytest.fixture
def small_df():
    return pd.DataFrame(
        {
            "product": ["Laptop", "Mouse", "Laptop", "Keyboard"],
            "revenue": [100, 10, 200, 30],
            "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-02-01", "2024-02-02"]),
        }
    )


def ask(dataset_id, question, session_id=None):
    body = {"question": question}
    if session_id:
        body["session_id"] = session_id
    response = client.post(f"/datasets/{dataset_id}/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---------- plan validation (the safety layer) ----------

def test_unknown_column_rejected(small_df):
    plan = QueryPlan(operation="aggregate", measure="profit", aggregation="sum")
    with pytest.raises(PlanError, match="no column"):
        validate_plan(plan, small_df)


def test_non_numeric_measure_rejected(small_df):
    plan = QueryPlan(operation="aggregate", measure="product", aggregation="sum")
    with pytest.raises(PlanError, match="numeric"):
        validate_plan(plan, small_df)


def test_names_and_values_resolved_ignoring_case(small_df):
    plan = QueryPlan(
        operation="aggregate", measure="Revenue", group_by=["PRODUCT"],
        filters=[Filter(column="Product", op="==", value="laptop")],
    )
    checked = validate_plan(plan, small_df)
    assert checked.measure == "revenue"
    assert checked.group_by == ["product"]
    assert checked.filters[0].value == "Laptop"
    assert checked.limit == 10  # default limit for grouped answers


def test_missing_values_rejected_and_injection_text_is_inert(small_df):
    for bad in ("Phone", "'; DROP TABLE sales; --"):
        plan = QueryPlan(
            operation="aggregate", measure="revenue",
            filters=[Filter(column="product", op="==", value=bad)],
        )
        with pytest.raises(PlanError, match="not found"):
            validate_plan(plan, small_df)
    assert len(small_df) == 4


def test_invalid_plan_shapes_rejected():
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({"operation": "exec", "code": "__import__('os')"})
    with pytest.raises(ValidationError):
        QueryPlan(operation="aggregate", measure="revenue", limit=500)
    with pytest.raises(ValidationError):
        QueryPlan(operation="aggregate", measure="revenue", group_by=["a", "b", "c"])


# ---------- keyword planner through the API ----------

def test_top_group_question(dataset_id):
    body = ask(dataset_id, "Which product has the highest revenue?")
    assert body["status"] == "ok"
    assert body["source"] == "rules"
    assert body["result"]["rows"] == [["Laptop", 200000]]
    assert "Laptop" in body["answer"] and "97.8%" in body["answer"]
    assert body["method"]


def test_follow_up_uses_previous_answer(dataset_id):
    first = ask(dataset_id, "Which product has the highest revenue?")
    second = ask(dataset_id, "How much revenue did it generate?", first["session_id"])
    assert second["status"] == "ok"
    assert second["plan"]["filters"][0]["column"] == "product"
    assert second["plan"]["filters"][0]["value"] == "Laptop"
    assert second["result"]["scalar"] == 200000


def test_top_n_question(dataset_id):
    body = ask(dataset_id, "Show the top 2 products by revenue")
    assert [r[0] for r in body["result"]["rows"]] == ["Laptop", "Keyboard"]
    assert body["result"]["row_count"] == 3
    assert body["result"]["truncated"] is True


def test_average_by_group_has_chart(dataset_id):
    body = ask(dataset_id, "What is the average revenue by region?")
    assert body["result"]["rows"][0] == ["South", 25600]
    assert body["result"]["chart"]["figure"]["data"][0]["type"] == "bar"


def test_monthly_trend(dataset_id):
    body = ask(dataset_id, "What is the monthly revenue trend?")
    assert body["result"]["kind"] == "trend"
    assert len(body["result"]["rows"]) == 4
    assert body["result"]["rows"][0] == ["2024-01", 50700]
    assert "incomplete" in body["answer"]
    assert body["result"]["chart"]["type"] == "line"


def test_row_count(dataset_id):
    assert ask(dataset_id, "How many rows are there?")["result"]["scalar"] == 8


def test_value_filters(dataset_id):
    body = ask(dataset_id, "Total revenue for Laptop in North")
    assert body["result"]["scalar"] == 100000
    assert len(body["plan"]["filters"]) == 2


def test_describe_measure(dataset_id):
    body = ask(dataset_id, "Describe the revenue")
    stats = {name: value for name, value in body["result"]["rows"]}
    assert body["result"]["kind"] == "describe"
    assert stats["count"] == 8 and stats["median"] == 25750 and stats["max"] == 50000


def test_unsupported_questions_get_suggestions(dataset_id):
    for question in ("Predict the revenue for next year", "blah blah blah"):
        body = ask(dataset_id, question)
        assert body["status"] == "unsupported"
        assert body["suggestions"]
        assert body["result"] is None


# ---------- AI planner ----------

def test_ai_plan_is_validated_and_executed(dataset_id, monkeypatch):
    seen = {}

    def fake(system, user, **kw):
        seen["user"] = user
        return TOP_PRODUCT_PLAN

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", fake)
    body = ask(dataset_id, "Which product earns the most?")
    assert body["source"] == "ai"
    assert body["result"]["rows"] == [["Laptop", 200000]]
    # only the schema goes to the AI, never individual rows
    assert "2024-01-12" not in seen["user"] and "2024-02-14" not in seen["user"]


def test_invalid_ai_plan_falls_back_to_rules(dataset_id, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        llm_service, "complete_json",
        lambda system, user, **kw: {**TOP_PRODUCT_PLAN, "measure": "profit"},
    )
    body = ask(dataset_id, "Which product has the highest revenue?")
    assert body["status"] == "ok"
    assert body["source"] == "rules"
    assert "keyword" in body["note"]


def test_garbage_ai_output_falls_back_to_rules(dataset_id, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", lambda system, user, **kw: {"foo": 1})
    body = ask(dataset_id, "Which product has the highest revenue?")
    assert body["status"] == "ok" and body["source"] == "rules"


# ---------- sessions and input validation ----------

def test_chat_history_endpoint(dataset_id):
    first = ask(dataset_id, "Which product has the highest revenue?")
    ask(dataset_id, "How many rows are there?", first["session_id"])
    r = client.get(f"/datasets/{dataset_id}/chat/{first['session_id']}")
    assert r.status_code == 200
    turns = r.json()["turns"]
    assert [t["question"] for t in turns][-1] == "How many rows are there?"
    assert len(turns) == 2
    assert client.get(f"/datasets/{dataset_id}/chat/abc").status_code == 400


def test_question_validation(dataset_id):
    url = f"/datasets/{dataset_id}/chat"
    assert client.post(url, json={"question": "   "}).status_code == 422
    assert client.post(url, json={"question": "x" * 501}).status_code == 422


def test_responses_are_json_safe(dataset_id):
    json.dumps(ask(dataset_id, "What is the monthly revenue trend?"))


def test_chat_unknown_dataset():
    r = client.post(f"/datasets/{'0' * 32}/chat", json={"question": "hi there"})
    assert r.status_code == 404