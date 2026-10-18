import asyncio
import sys
import types

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agents.query_executor import execute_plan
from agents.query_plan import Filter, PlanError, QueryPlan, validate_plan
from agents.sql_agent import NotInSql, plan_to_sql
from agents.sql_guard import run_select
from config import settings
from main import app
from services import llm_service, rate_limit
from utils.upload_limit import UploadSizeLimit

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "qty": [1, 2, 3],
            "name": ["a", "b", "c"],
            "day": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        }
    )


def plan(**kwargs):
    return QueryPlan(operation="aggregate", measure="qty", **kwargs)


# ---------- the OpenAI wrapper (tested with a fake openai package, no network) ----------

def fake_openai(monkeypatch, content=None, error=None):
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(("create", kwargs))
            if error:
                raise error
            message = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    class Client:
        chat = types.SimpleNamespace(completions=Completions())

        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

    module = types.ModuleType("openai")
    module.OpenAI = Client
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    return calls


def test_the_ai_wrapper_sends_the_expected_request(monkeypatch):
    calls = fake_openai(monkeypatch, content='{"summary": "hi"}')
    assert llm_service.complete_json("system text", "user text") == {"summary": "hi"}
    client_options, request = calls[0][1], calls[1][1]
    assert client_options["api_key"] == "test-key"
    assert request["model"] == settings.openai_model
    assert request["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in request["messages"]] == ["system", "user"]


@pytest.mark.parametrize("content, message", [("not json at all", "unreadable"), ("[1, 2]", "unexpected")])
def test_bad_ai_answers_are_reported_safely(monkeypatch, content, message):
    fake_openai(monkeypatch, content=content)
    with pytest.raises(llm_service.LLMUnavailable, match=message):
        llm_service.complete_json("s", "u")


def test_ai_failures_never_leak_details(monkeypatch):
    fake_openai(monkeypatch, error=RuntimeError("401 invalid key sk-secret-999"))
    with pytest.raises(llm_service.LLMUnavailable) as info:
        llm_service.complete_json("s", "u")
    assert "sk-secret-999" not in str(info.value)
    assert "not available" in str(info.value)


def test_an_empty_ai_answer_becomes_an_empty_object(monkeypatch):
    fake_openai(monkeypatch, content=None)
    assert llm_service.complete_json("s", "u") == {}


def test_a_missing_openai_package_is_handled(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(llm_service.LLMUnavailable, match="not installed"):
        llm_service.complete_json("s", "u")


def test_no_key_means_no_ai_call(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "  ")
    assert llm_service.is_configured() is False
    with pytest.raises(llm_service.LLMUnavailable, match="no OpenAI API key"):
        llm_service.complete_json("s", "u")


# ---------- the plan validator (the safety layer for chat questions) ----------

def test_numeric_filters_reject_text_operations_and_non_numbers(df):
    with pytest.raises(PlanError, match="numeric"):
        validate_plan(plan(filters=[Filter(column="qty", op="contains", value="1")]), df)
    with pytest.raises(PlanError, match="not a number"):
        validate_plan(plan(filters=[Filter(column="qty", op="==", value="abc")]), df)
    ok = validate_plan(plan(filters=[Filter(column="qty", op=">", value="1")]), df)
    assert ok.filters[0].op == ">"


def test_date_filters_reject_bad_operations_and_values(df):
    with pytest.raises(PlanError, match="date column"):
        validate_plan(plan(filters=[Filter(column="day", op="in", value=["2024-01-01"])]), df)
    with pytest.raises(PlanError, match="not a valid date"):
        validate_plan(plan(filters=[Filter(column="day", op=">=", value="not a date")]), df)
    ok = validate_plan(plan(filters=[Filter(column="day", op=">=", value="2024-01-02")]), df)
    assert ok.filters[0].column == "day"


def test_text_filters_reject_comparisons_and_resolve_values(df):
    with pytest.raises(PlanError, match="text column"):
        validate_plan(plan(filters=[Filter(column="name", op=">", value="a")]), df)
    contains = validate_plan(plan(filters=[Filter(column="name", op="contains", value="A")]), df)
    assert contains.filters[0].value == "A"
    several = validate_plan(plan(filters=[Filter(column="name", op="in", value=["A", "b"])]), df)
    assert several.filters[0].value == ["a", "b"]


@pytest.mark.parametrize(
    "kwargs, drop_day, message",
    [
        ({"operation": "unsupported", "reason": "nope"}, False, "nope"),
        ({"operation": "describe"}, False, "describe"),
        ({"operation": "aggregate", "aggregation": "sum"}, False, "numeric column to calculate"),
        ({"operation": "aggregate", "measure": "qty", "group_by": ["day"]}, False, "date column"),
        ({"operation": "trend", "measure": "qty"}, True, "no date column"),
        ({"operation": "trend", "measure": "qty", "date_column": "name"}, False, "not a date column"),
        ({"operation": "change_drivers", "measure": "qty", "aggregation": "mean", "period": "x"}, False, "totals"),
    ],
)
def test_plan_level_validation_errors(df, kwargs, drop_day, message):
    frame = df.drop(columns="day") if drop_day else df
    with pytest.raises(PlanError, match=message):
        validate_plan(QueryPlan(**kwargs), frame)


# ---------- the executor's filters ----------

def count(frame, *filters):
    checked = validate_plan(
        QueryPlan(operation="aggregate", aggregation="count", filters=list(filters)), frame
    )
    return execute_plan(checked, frame)


def test_every_filter_operator_selects_the_right_rows(df):
    cases = [
        (Filter(column="name", op="!=", value="a"), 2),
        (Filter(column="name", op="in", value=["a", "b"]), 2),
        (Filter(column="name", op="contains", value="A"), 1),
        (Filter(column="qty", op=">", value=1), 2),
        (Filter(column="qty", op="<=", value=2), 2),
        (Filter(column="qty", op="==", value=3), 1),
        (Filter(column="day", op=">=", value="2024-01-02"), 2),
        (Filter(column="day", op="==", value="2024-01-02"), 1),
    ]
    for rule, expected in cases:
        assert count(df, rule)["scalar"] == expected, rule


def test_filters_that_match_nothing_give_an_empty_result(df):
    result = count(df, Filter(column="qty", op=">", value=100))
    assert result["kind"] == "empty" and result["matched_rows"] == 0


# ---------- the SQL compiler ----------

def sql_for(frame, **kwargs):
    checked = validate_plan(QueryPlan(operation="aggregate", aggregation="count", **kwargs), frame)
    sql = plan_to_sql(checked, frame)
    return sql, run_select(frame, sql)["rows"]


def test_quotes_in_values_are_escaped():
    frame = pd.DataFrame({"name": ["O'Brien", "x", "y"], "qty": [1, 2, 3]})
    sql, rows = sql_for(frame, filters=[Filter(column="name", op="==", value="O'Brien")])
    assert "'O''Brien'" in sql
    assert rows == [[1]]


def test_operators_become_valid_sql(df):
    sql, rows = sql_for(df, filters=[Filter(column="name", op="in", value=["a", "b"])])
    assert "IN ('a', 'b')" in sql and rows == [[2]]
    sql, rows = sql_for(df, filters=[Filter(column="qty", op=">", value=1)])
    assert "> 1.0" in sql and rows == [[2]]
    sql, rows = sql_for(df, filters=[Filter(column="day", op=">=", value="2024-01-02")])
    assert "'2024-01-02'" in sql and rows == [[2]]
    sql, rows = sql_for(df, filters=[Filter(column="name", op="!=", value="a")])
    assert "<>" in sql and rows == [[2]]


def test_like_wildcards_in_values_are_escaped():
    frame = pd.DataFrame({"note": ["50%_off", "500 items", "none"], "qty": [1, 2, 3]})
    sql, rows = sql_for(frame, filters=[Filter(column="note", op="contains", value="0%_")])
    assert "ESCAPE" in sql and "\\%" in sql
    assert rows == [[1]]  # unescaped, the % and _ would also match "500 items"


def test_distinct_counts_compile_to_sql(df):
    checked = validate_plan(QueryPlan(operation="aggregate", measure="name", aggregation="nunique"), df)
    sql = plan_to_sql(checked, df)
    assert "COUNT(DISTINCT" in sql
    assert run_select(df, sql)["rows"] == [[3]]


def test_shapes_sql_cannot_express_are_refused(df):
    median = validate_plan(QueryPlan(operation="aggregate", measure="qty", aggregation="median"), df)
    with pytest.raises(NotInSql, match="Median"):
        plan_to_sql(median, df)
    weekly = validate_plan(QueryPlan(operation="trend", measure="qty", time_grain="week"), df)
    with pytest.raises(NotInSql, match="Weekly"):
        plan_to_sql(weekly, df)
    infinite = validate_plan(plan(filters=[Filter(column="qty", op=">", value="inf")]), df)
    with pytest.raises(NotInSql, match="number"):
        plan_to_sql(infinite, df)
    describe = validate_plan(QueryPlan(operation="describe", measure="qty"), df)
    with pytest.raises(NotInSql, match="SQL mode"):
        plan_to_sql(describe, df)


# ---------- the upload guard and rate limiter ----------

async def _through_the_guard(method, path, headers):
    seen = []

    async def app_stub(scope, receive, send):
        seen.append("app")

    async def send(message):
        seen.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    await UploadSizeLimit(app_stub)(scope, receive, send)
    return seen


def through_the_guard(method, path, headers):
    return asyncio.run(_through_the_guard(method, path, headers))


def test_the_upload_guard_checks_the_content_length_header():
    assert through_the_guard("POST", "/upload", [])[0]["status"] == 411
    assert through_the_guard("POST", "/upload", [(b"content-length", b"abc")])[0]["status"] == 400
    assert through_the_guard("POST", "/upload", [(b"content-length", b"10")]) == ["app"]
    assert through_the_guard("POST", "/other", []) == ["app"]  # only /upload is guarded
    assert through_the_guard("GET", "/upload", []) == ["app"]


def test_the_proxy_header_is_trusted_only_when_enabled(monkeypatch):
    request = types.SimpleNamespace(
        headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"}, client=types.SimpleNamespace(host="9.9.9.9")
    )
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    assert rate_limit.client_key(request) == "9.9.9.9"
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    assert rate_limit.client_key(request) == "1.2.3.4"
    assert rate_limit.client_key(types.SimpleNamespace(headers={}, client=None)) == "unknown"


def test_the_limiter_forgets_idle_clients(monkeypatch):
    now = [0.0]
    limiter = rate_limit.RateLimiter(clock=lambda: now[0])
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_KEYS", 2)
    limiter.check("a", 5, 60)
    limiter.check("b", 5, 60)
    now[0] = 100
    limiter.check("c", 5, 60)
    assert list(limiter._hits) == ["c"]


# ---------- unusual files ----------

def upload(content):
    return client.post("/upload", files={"file": ("d.csv", content)})


def test_latin1_csv_files_are_read():
    r = upload("city,n\nZ\xfcrich,1\nBern,2\n".encode("latin-1"))
    assert r.status_code == 200
    assert "Z\u00fcrich" in {row["city"] for row in r.json()["preview"]}


def test_header_only_and_blank_csv_files_are_refused():
    assert upload(b"a,b\n").status_code == 422
    blank = upload(b"\n\n")
    assert blank.status_code == 400 and "no data" in blank.json()["error"]


def test_files_slightly_over_the_limit_are_refused_by_the_validator(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    content = b"a,b\n" + b"1,2\n" * 266_000  # a little over 1 MB, under the early-reject margin
    r = upload(content)
    assert r.status_code == 413 and "too large" in r.json()["error"]