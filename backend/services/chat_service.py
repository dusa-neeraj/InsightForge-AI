from typing import Any

from agents import ai_agent
from agents.explainer import build_answer, method_steps
from agents.query_executor import execute_plan
from agents.query_plan import PlanError, QueryPlan, validate_plan
from services import file_service
from utils.helpers import new_dataset_id  # random 32-character hex id, reused for sessions


def _run(plan: QueryPlan, df) -> tuple[QueryPlan, dict[str, Any]]:
    checked = validate_plan(plan, df)
    return checked, execute_plan(checked, df)


def ask(dataset_id: str, question: str, session_id: str | None = None) -> dict[str, Any]:
    df = file_service.load_clean_dataset(dataset_id)
    session_id = session_id or new_dataset_id()
    history = file_service.load_chat_history(dataset_id, session_id)[-3:]
    schema = ai_agent.build_schema(df)
    plan, source, note = ai_agent.make_plan(question, schema, history)

    checked: QueryPlan | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    if plan.operation != "unsupported":
        try:
            checked, result = _run(plan, df)
        except PlanError as exc:
            error = str(exc)
            if source == "ai":  # second chance with the keyword planner
                fallback = ai_agent.rule_plan(question, schema, history)
                if fallback.operation != "unsupported":
                    try:
                        checked, result = _run(fallback, df)
                        source, error = "rules", None
                        note = "The AI plan could not be run, so keyword matching was used."
                    except PlanError:
                        pass

    suggestions: list[str] = []
    if checked is not None and result is not None:
        status = "ok"
        answer = build_answer(checked, result)
        method = method_steps(checked, result)
    elif plan.operation == "unsupported":
        status, method = "unsupported", []
        answer = plan.reason or "I can't answer that with the data in this dataset."
        suggestions = ai_agent.suggest_questions(schema)
    else:
        status, method = "error", []
        answer = error or "I couldn't run that question."
        suggestions = ai_agent.suggest_questions(schema)

    file_service.append_chat_turn(dataset_id, session_id, {
        "question": question,
        "answer": answer,
        "status": status,
        "plan": checked.model_dump() if checked else None,
        "focus": (result or {}).get("focus", {}),
    })

    return {
        "session_id": session_id,
        "question": question,
        "status": status,
        "answer": answer,
        "method": method,
        "plan": checked.model_dump() if checked else None,
        "result": result,
        "source": source,
        "note": note,
        "suggestions": suggestions,
    }