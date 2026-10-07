import re
from typing import Any

from agents.query_plan import QueryPlan

MONTH_WORDS = (
    "january|february|march|april|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
)
MONTH_RE = re.compile(rf"\b({MONTH_WORDS})\b(?:\s+(\d{{4}}))?")
MAY_RE = re.compile(r"\b(?:in|for|during|of)\s+(may)\b(?:\s+(\d{4}))?")  # "may" is also a verb
LATEST_RE = re.compile(r"\b(?:last|this)\s+(month|week)\b|\b(?:latest|recent|recently|lately)\b")


def _unsupported(reason: str) -> QueryPlan:
    return QueryPlan(operation="unsupported", reason=reason)


def why_plan(question: str, schema: dict[str, Any], measure: str | None) -> QueryPlan:
    """Turn 'why did X change in <period>' into a change_drivers plan."""
    q = question.lower()
    if not schema["date_columns"]:
        return _unsupported("Explaining a change needs a date column, and this dataset has none.")
    measure = measure or schema["default_measure"]
    if not measure:
        return _unsupported("Explaining a change needs a numeric column to measure.")
    if schema["aggregations"].get(measure) != "sum":
        return _unsupported(
            f"I can explain changes in totals, but '{measure}' is an average-type column, "
            f"so a total-based explanation would be misleading."
        )

    period, grain = "latest", None
    found = MONTH_RE.search(q) or MAY_RE.search(q)
    if found:
        period = f"{found.group(1)} {found.group(2)}" if found.group(2) else found.group(1)
        grain = "month"
    else:
        latest = LATEST_RE.search(q)
        if latest and latest.group(1):
            grain = latest.group(1)

    return QueryPlan(
        operation="change_drivers", measure=measure, aggregation="sum",
        period=period, time_grain=grain, date_column=schema["date_columns"][0],
    )