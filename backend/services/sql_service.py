from typing import Any

from agents import ai_agent, sql_agent, sql_guard
from agents.narrator import clean_text
from agents.profiling import column_kind
from agents.query_plan import PlanError, validate_plan
from services import file_service, llm_service
from utils.errors import SqlError, SqlRejected

EMPTY = {"columns": [], "rows": [], "row_count": 0, "truncated": False, "elapsed_ms": 0}


def _response(status: str, source: str, question: str | None, sql: str | None = None,
              explanation: str | None = None, message: str | None = None,
              note: str | None = None, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status, "source": source, "question": question, "sql": sql,
        "explanation": explanation, "message": message, "note": note, **(result or EMPTY),
    }


def _failure(exc: SqlError) -> str:
    return "rejected" if isinstance(exc, SqlRejected) else "error"


# ---------- the user wrote the SQL ----------

def _run_user_sql(df, sql: str) -> dict[str, Any]:
    try:
        result = sql_guard.run_select(df, sql)
    except SqlError as exc:
        return _response(_failure(exc), "user", None, sql.strip(), message=str(exc))
    return _response("ok", "user", None, sql.strip(), result=result)


# ---------- the AI writes the SQL ----------

def _ai_question(df, schema: dict[str, Any], question: str) -> dict[str, Any]:
    schema_view = sql_agent.sql_schema(df, schema)
    previous: str | None = None
    error: str | None = None
    status = "error"

    for _ in range(2):  # the first try, then one repair attempt
        raw = llm_service.complete_json(
            sql_agent.SQL_PROMPT, sql_agent.build_payload(question, schema_view, previous, error),
            max_tokens=500,
        )
        sql = raw.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            reason = raw.get("reason")
            message = clean_text(reason, 300) if isinstance(reason, str) and reason.strip() \
                else "The AI could not write a query for that question."
            return _response("unsupported", "ai", question, message=message)
        explanation = raw.get("explanation")
        explanation = clean_text(explanation, 300) if isinstance(explanation, str) else None
        try:
            result = sql_guard.run_select(df, sql)
            return _response("ok", "ai", question, sql.strip(), explanation, result=result)
        except SqlError as exc:
            previous, error, status = sql.strip(), str(exc), _failure(exc)

    return _response(status, "ai", question, previous, message=error,
                     note="The AI's query failed twice, so nothing was shown.")


# ---------- offline: keyword plan compiled to SQL ----------

def _rules_question(df, schema: dict[str, Any], question: str, note: str | None) -> dict[str, Any]:
    plan = ai_agent.rule_plan(question, schema, [])
    if plan.operation == "unsupported":
        return _response("unsupported", "rules", question, message=plan.reason, note=note)
    try:
        checked = validate_plan(plan, df)
        sql = sql_agent.plan_to_sql(checked, df)
        result = sql_guard.run_select(df, sql)
    except PlanError as exc:
        return _response("error", "rules", question, message=str(exc), note=note)
    except sql_agent.NotInSql as exc:
        return _response("unsupported", "rules", question, message=str(exc), note=note)
    except SqlError as exc:
        return _response(_failure(exc), "rules", question, message=str(exc), note=note)
    return _response("ok", "rules", question, sql, sql_agent.describe_plan(checked),
                     note=note, result=result)


def _run_question(df, question: str) -> dict[str, Any]:
    schema = ai_agent.build_schema(df)
    if llm_service.is_configured():
        try:
            return _ai_question(df, schema, question)
        except llm_service.LLMUnavailable as exc:
            note = str(exc)
    else:
        note = ("Answered without AI, so only simple questions work. "
                "You can also type your own SQL.")
    return _rules_question(df, schema, question, note)


# ---------- public functions used by the routes ----------

def run(dataset_id: str, question: str | None, sql: str | None) -> dict[str, Any]:
    df = file_service.load_clean_dataset(dataset_id)
    if sql:
        return _run_user_sql(df, sql)
    return _run_question(df, question or "")


def schema(dataset_id: str) -> dict[str, Any]:
    df = file_service.load_clean_dataset(dataset_id)
    return {
        "table": sql_guard.TABLE,
        "rows": int(len(df)),
        "columns": [
            {"name": c, "type": sql_guard.sqlite_type(df[c]), "kind": column_kind(df[c])}
            for c in df.columns
        ],
        "notes": [
            f"Query the table named {sql_guard.TABLE}. Only SELECT statements are allowed.",
            "Dates are stored as text like 2024-03-15. Use strftime('%Y-%m', column) to group by month.",
            f"Results are limited to {sql_guard.MAX_ROWS:,} rows and {sql_guard.TIMEOUT_SECONDS:g} seconds.",
            "SQLite has no MEDIAN or STDDEV function.",
        ],
    }