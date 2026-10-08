import re
from typing import Any

from agents import ai_agent
from agents.explainer import build_answer, method_steps
from agents.query_executor import execute_plan
from agents.query_plan import PlanError, QueryPlan, validate_plan
from agents.question_splitter import MAX_PARTS, split_question
from services import analysis_service, file_service
from utils.helpers import new_dataset_id  # random 32-character hex id, reused for sessions

INSIGHT_RE = re.compile(
    r"\b(insights?|key findings?|main findings?|important findings?|highlights|"
    r"what stands out|interesting (?:things|patterns|findings))\b"
)
RECOMMEND_RE = re.compile(
    r"\b(recommendations?|recommend|actionable|next steps|what should (?:i|we) do)\b"
)
VISUAL_RE = re.compile(r"\b(visuali[sz]ations?|charts?|graphs?|plots?)\b")
DEFAULT_COUNT = 5
MAX_COUNT = 12


def _wanted(question: str) -> int:
    number = re.search(r"\b(\d{1,2})\b", question.lower())
    return min(max(int(number.group(1)), 1), MAX_COUNT) if number else DEFAULT_COUNT


def _reply(status: str, answer: str, *, method=None, plan=None, result=None, source="rules",
           note=None, suggestions=None, focus=None) -> dict[str, Any]:
    return {
        "status": status, "answer": answer, "method": method or [], "plan": plan,
        "result": result, "source": source, "note": note,
        "suggestions": suggestions or [], "focus": focus or {},
    }


def _run(plan: QueryPlan, df) -> tuple[QueryPlan, dict[str, Any]]:
    checked = validate_plan(plan, df)
    return checked, execute_plan(checked, df)


# ---------- special requests answered without a query plan ----------

def _insights_part(dataset_id: str, question: str) -> dict[str, Any]:
    insights = analysis_service.calculated_insights(dataset_id)[: _wanted(question)]
    if insights:
        lines = [f"{i}. {item['message']}" for i, item in enumerate(insights, start=1)]
        answer = (
            f"Here are the {len(insights)} most important findings:\n"
            + "\n".join(lines)
            + "\n\nOpen the AI Insights page to see the evidence behind each one."
        )
    else:
        answer = "I couldn't find any notable patterns in this dataset."
    method = [
        "Calculated findings from the data: breakdowns, trends, relationships, outliers and data quality",
        f"Ranked them by importance and kept the top {len(insights)}",
    ]
    return _reply("ok", answer, method=method, source="insights")


def _recommendations_part(dataset_id: str, question: str) -> dict[str, Any]:
    narration = analysis_service.get_insights(dataset_id)["narration"]
    recs = narration["recommendations"][: _wanted(question)]
    if not recs:
        return _reply("ok", "I don't have specific recommendations for this dataset yet.",
                      source="insights")
    lines = [f"{i}. {text}" for i, text in enumerate(recs, start=1)]
    note = None if narration["source"] == "ai" else (
        "These come from the rule-based analysis. With AI turned on they are more specific."
    )
    return _reply("ok", "Suggested next steps:\n" + "\n".join(lines),
                  method=["Used the calculated insights to suggest next steps"],
                  source="insights", note=note)


# ---------- the normal path: question -> plan -> validated calculation ----------

def _planner_part(df, schema: dict[str, Any], question: str,
                  history: list[dict[str, Any]]) -> dict[str, Any]:
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

    if checked is not None and result is not None:
        return _reply(
            "ok", build_answer(checked, result), method=method_steps(checked, result),
            plan=checked.model_dump(), result=result, source=source, note=note,
            focus=result.get("focus", {}),
        )
    suggestions = ai_agent.suggest_questions(schema)
    if plan.operation == "unsupported":
        answer = plan.reason or "I can't answer that with the data in this dataset."
        return _reply("unsupported", answer, source=source, note=note, suggestions=suggestions)
    return _reply("error", error or "I couldn't run that question.", source=source, note=note,
                  suggestions=suggestions)


def _answer_single(dataset_id: str, df, schema: dict[str, Any], question: str,
                   history: list[dict[str, Any]]) -> dict[str, Any]:
    q = question.lower()
    if RECOMMEND_RE.search(q):
        return _recommendations_part(dataset_id, question)
    if INSIGHT_RE.search(q):
        return _insights_part(dataset_id, question)

    reply = _planner_part(df, schema, question, history)
    if reply["status"] == "unsupported" and VISUAL_RE.search(q):
        return _reply(
            "ok",
            "Charts for your data are on the Dashboard page. They are chosen automatically "
            "from the column types, and each one explains why it was picked.",
            method=["Charts are selected from the types and shapes of your columns"],
            source="dashboard",
        )
    return reply


# ---------- public entry point ----------

def ask(dataset_id: str, question: str, session_id: str | None = None) -> dict[str, Any]:
    session_id = session_id or new_dataset_id()
    df = file_service.load_clean_dataset(dataset_id)
    history = file_service.load_chat_history(dataset_id, session_id)[-3:]
    schema = ai_agent.build_schema(df)
    questions = split_question(question)

    parts: list[dict[str, Any]] | None = None
    if len(questions) == 1:
        reply = _answer_single(dataset_id, df, schema, questions[0], history)
    else:  # a message with several requests: answer each one on its own
        parts = []
        for part_question in questions[:MAX_PARTS]:
            part = _answer_single(dataset_id, df, schema, part_question, history)
            parts.append({"question": part_question, **part})
        answered = sum(1 for p in parts if p["status"] == "ok")
        lines = [f"{i}. {p['question']}: {p['answer']}" for i, p in enumerate(parts, start=1)]
        text = f"Answered {answered} of {len(parts)} parts of your request.\n" + "\n".join(lines)
        note = f"Only the first {MAX_PARTS} parts were answered." if len(questions) > MAX_PARTS else None
        reply = _reply("ok" if answered else "unsupported", text, source="multi", note=note)

    file_service.append_chat_turn(dataset_id, session_id, {
        "question": question,
        "answer": reply["answer"],
        "status": reply["status"],
        "plan": reply["plan"],
        "focus": reply["focus"],
    })
    return {
        "session_id": session_id,
        "question": question,
        "status": reply["status"],
        "answer": reply["answer"],
        "method": reply["method"],
        "plan": reply["plan"],
        "result": reply["result"],
        "source": reply["source"],
        "note": reply["note"],
        "suggestions": reply["suggestions"],
        "parts": parts,
    }