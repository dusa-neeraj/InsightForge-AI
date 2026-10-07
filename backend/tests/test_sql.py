import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents import sql_guard
from agents.sql_guard import run_select
from config import settings
from main import app
from services import llm_service
from utils.errors import SqlError, SqlRejected

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

GOOD_SQL = ("SELECT region, AVG(revenue) AS avg_revenue FROM data "
            "GROUP BY region ORDER BY avg_revenue DESC")


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def sales_df():
    df = pd.read_csv(io.BytesIO(CSV))
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


@pytest.fixture
def dataset_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    return client.post("/upload", files={"file": ("sales.csv", CSV)}).json()["dataset_id"]


def sql_call(dataset_id, **body):
    response = client.post(f"/datasets/{dataset_id}/sql", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---------- queries that should work ----------

def test_select_with_grouping(sales_df):
    result = run_select(
        sales_df,
        "SELECT product, SUM(revenue) AS total FROM data GROUP BY product ORDER BY total DESC",
    )
    assert result["columns"] == ["product", "total"]
    assert result["rows"][0] == ["Laptop", 200000]
    assert result["truncated"] is False


def test_date_functions_work_on_iso_text(sales_df):
    result = run_select(
        sales_df,
        "SELECT strftime('%Y-%m', order_date) AS month, SUM(revenue) AS total "
        "FROM data GROUP BY month ORDER BY month",
    )
    assert len(result["rows"]) == 4
    assert result["rows"][0] == ["2024-01", 50700]


def test_simple_queries_are_allowed(sales_df):
    assert run_select(sales_df, "SELECT COUNT(*) FROM data")["rows"] == [[8]]
    assert run_select(sales_df, "SELECT COUNT(*) FROM data;")["rows"] == [[8]]
    assert run_select(sales_df, "SELECT 1 + 1 AS two")["rows"] == [[2]]
    like = run_select(sales_df, "SELECT COUNT(*) FROM data WHERE product LIKE '%top%'")
    assert like["rows"] == [[4]]


# ---------- queries that must be refused ----------

@pytest.mark.parametrize("sql", [
    "DROP TABLE data",
    "INSERT INTO data VALUES (1)",
    "UPDATE data SET revenue = 0",
    "DELETE FROM data",
    "CREATE TABLE x (a int)",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA table_info(data)",
])
def test_non_select_statements_rejected(sales_df, sql):
    with pytest.raises(SqlRejected):
        run_select(sales_df, sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM data; DROP TABLE data",
    "SELECT 1; SELECT 2",
    "SELECT * FROM data -- hi",
    "SELECT /* x */ 1",
    "",
    "   ",
])
def test_multiple_statements_comments_and_empty_rejected(sales_df, sql):
    with pytest.raises(SqlRejected):
        run_select(sales_df, sql)


@pytest.mark.parametrize("sql", [
    "WITH x AS (SELECT 1) DELETE FROM data",
    "SELECT 1 UNION SELECT 2; DELETE FROM data",
])
def test_writes_hidden_inside_selects_rejected(sales_df, sql):
    with pytest.raises(SqlRejected):
        run_select(sales_df, sql)


@pytest.mark.parametrize("sql", [
    "SELECT random()",
    "SELECT randomblob(16)",
    "SELECT zeroblob(1000)",
    "SELECT printf('%d', 1)",
    'SELECT * FROM "sqlite_master"',  # quoted, so only the authorizer can catch it
])
def test_authorizer_blocks_unlisted_functions_and_tables(sales_df, sql):
    with pytest.raises(SqlRejected, match="isn't allowed"):
        run_select(sales_df, sql)


def test_pragma_table_functions_rejected(sales_df):
    with pytest.raises(SqlRejected, match="System"):
        run_select(sales_df, "SELECT * FROM pragma_table_info('data')")


# ---------- failures that are not security problems ----------

def test_unknown_column_is_a_friendly_error(sales_df):
    with pytest.raises(SqlError) as info:
        run_select(sales_df, "SELECT nope FROM data")
    assert not isinstance(info.value, SqlRejected)
    assert "no such column" in str(info.value)


def test_result_rows_are_capped():
    df = pd.DataFrame({"x": range(1500)})
    result = run_select(df, "SELECT * FROM data")
    assert len(result["rows"]) == sql_guard.MAX_ROWS
    assert result["truncated"] is True


def test_slow_queries_are_stopped(monkeypatch):
    monkeypatch.setattr(sql_guard, "TIMEOUT_SECONDS", 0.2)
    df = pd.DataFrame({"x": range(300)})
    with pytest.raises(SqlError) as info:
        run_select(df, "SELECT COUNT(*) FROM data a, data b, data c, data d")
    assert not isinstance(info.value, SqlRejected)
    assert "stopped" in str(info.value)


def test_results_are_json_safe(sales_df):
    json.dumps(run_select(
        sales_df, "SELECT region, AVG(revenue) AS a, MIN(order_date) AS d FROM data GROUP BY region"
    ))


# ---------- natural language through the API ----------

def test_offline_questions_become_sql_and_match_the_chat(dataset_id):
    def chat_rows(question):
        r = client.post(f"/datasets/{dataset_id}/chat", json={"question": question})
        return r.json()["result"]["rows"]

    top = sql_call(dataset_id, question="Which product has the highest revenue?")
    assert top["status"] == "ok" and top["source"] == "rules"
    assert 'GROUP BY "product"' in top["sql"]
    assert top["rows"] == [["Laptop", 200000]]
    assert top["rows"] == chat_rows("Which product has the highest revenue?")

    top_two = sql_call(dataset_id, question="Show the top 2 products by revenue")
    assert "LIMIT 2" in top_two["sql"]
    assert top_two["rows"] == chat_rows("Show the top 2 products by revenue")

    filtered = sql_call(dataset_id, question="Total revenue for Laptop in North")
    assert "WHERE" in filtered["sql"]
    assert filtered["rows"] == [[100000]]

    trend = sql_call(dataset_id, question="What is the monthly revenue trend?")
    assert len(trend["rows"]) == 4
    assert trend["rows"][0] == ["2024-01", 50700]


def test_ai_generated_sql_is_validated_and_run(dataset_id, monkeypatch):
    seen = []

    def fake(system, user, **kw):
        seen.append(user)
        return {"sql": GOOD_SQL, "explanation": "Average revenue per region."}

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", fake)
    body = sql_call(dataset_id, question="Which region earns more per order?")
    assert body["status"] == "ok" and body["source"] == "ai"
    assert body["rows"][0] == ["South", 25600]
    assert body["explanation"] == "Average revenue per region."
    # the AI sees the schema, never individual rows
    assert "2024-01-12" not in seen[0] and "2024-02-14" not in seen[0]


def test_dangerous_ai_sql_is_rejected_then_repaired(dataset_id, monkeypatch):
    calls = []

    def fake(system, user, **kw):
        calls.append(user)
        if len(calls) == 1:
            return {"sql": "DROP TABLE data", "explanation": "oops"}
        return {"sql": GOOD_SQL, "explanation": "Average revenue per region."}

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", fake)
    body = sql_call(dataset_id, question="Which region earns more per order?")
    assert body["status"] == "ok"
    assert len(calls) == 2
    assert "DROP TABLE data" in calls[1] and "Only SELECT" in calls[1]  # the error went back


def test_ai_sql_rejected_twice_runs_nothing(dataset_id, monkeypatch):
    calls = []

    def fake(system, user, **kw):
        calls.append(user)
        return {"sql": "DELETE FROM data"}

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(llm_service, "complete_json", fake)
    body = sql_call(dataset_id, question="Remove everything")
    assert body["status"] == "rejected"
    assert body["sql"] == "DELETE FROM data"
    assert body["rows"] == [] and len(calls) == 2
    assert sql_call(dataset_id, sql="SELECT COUNT(*) FROM data")["rows"] == [[8]]


def test_unsupported_questions(dataset_id, monkeypatch):
    summary = sql_call(dataset_id, question="Describe the revenue")
    assert summary["status"] == "unsupported" and "SQL mode" in summary["message"]
    assert sql_call(dataset_id, question="blah blah blah")["status"] == "unsupported"

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        llm_service, "complete_json",
        lambda system, user, **kw: {"sql": None, "reason": "That needs data we don't have."},
    )
    body = sql_call(dataset_id, question="What is the weather?")
    assert body["status"] == "unsupported"
    assert "data we don't have" in body["message"]


# ---------- user-written SQL, validation and schema ----------

def test_user_written_sql_through_the_api(dataset_id):
    ok = sql_call(
        dataset_id,
        sql="SELECT product, SUM(revenue) AS total FROM data GROUP BY product ORDER BY total DESC",
    )
    assert ok["status"] == "ok" and ok["source"] == "user"
    assert ok["rows"][0] == ["Laptop", 200000]

    rejected = sql_call(dataset_id, sql="DROP TABLE data")
    assert rejected["status"] == "rejected" and "Only SELECT" in rejected["message"]
    assert sql_call(dataset_id, sql="SELECT COUNT(*) FROM data")["rows"] == [[8]]

    failed = sql_call(dataset_id, sql="SELECT nope FROM data")
    assert failed["status"] == "error" and "no such column" in failed["message"]


def test_request_validation(dataset_id):
    url = f"/datasets/{dataset_id}/sql"
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"question": "a", "sql": "SELECT 1"}).status_code == 422
    assert client.post(url, json={"sql": "x" * 2001}).status_code == 422


def test_sql_schema_endpoint(dataset_id):
    body = client.get(f"/datasets/{dataset_id}/sql/schema").json()
    types = {c["name"]: c["type"] for c in body["columns"]}
    assert body["table"] == "data" and body["rows"] == 8
    assert types["order_date"] == "TEXT" and types["revenue"] == "INTEGER"
    assert body["notes"]


def test_sql_unknown_dataset():
    r = client.post(f"/datasets/{'0' * 32}/sql", json={"sql": "SELECT 1"})
    assert r.status_code == 404