from typing import Any

from agents.analysis import _fmt
from agents.query_plan import QueryPlan

OP_WORDS = {"==": "is", "!=": "is not", ">": "is above", ">=": "is at least",
            "<": "is below", "<=": "is at most", "in": "is one of", "contains": "contains"}


def _text(value: Any) -> str:
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


def describe_filters(plan: QueryPlan) -> list[str]:
    return [f"{f.column} {OP_WORDS[f.op]} {_text(f.value)}" for f in plan.filters]


def _scope(plan: QueryPlan) -> str:
    filters = describe_filters(plan)
    return " where " + " and ".join(filters) if filters else ""


def method_steps(plan: QueryPlan, result: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    if plan.filters:
        steps.append(
            "Kept only rows where " + " and ".join(describe_filters(plan))
            + f" ({result['matched_rows']:,} of {result['total_rows']:,} rows)"
        )
    kind = result["kind"]
    if kind == "empty":
        steps.append("No rows were left to calculate with")
    elif kind == "trend":
        steps.append(f"Grouped rows by {result['grain']} using '{result['date_column']}'")
        steps.append(f"Calculated the {result['label']} for each {result['grain']}")
    elif kind == "describe":
        steps.append(f"Calculated summary statistics for '{plan.measure}'")
    elif plan.group_by:
        steps.append("Grouped rows by " + " and ".join(f"'{c}'" for c in plan.group_by))
        steps.append(f"Calculated the {result['label']} for each group")
        direction = "highest" if plan.sort == "desc" else "lowest"
        steps.append(f"Sorted {direction} first and kept the top {plan.limit or 10}")
    else:
        steps.append(f"Calculated the {result['label']} over all matching rows")
    return steps


def build_answer(plan: QueryPlan, result: dict[str, Any]) -> str:
    """Write the answer from the computed numbers only."""
    kind = result["kind"]
    if kind == "empty":
        return result.get("note") or "No rows match those filters, so there is nothing to calculate."

    label, scope, rows = result["label"], _scope(plan), result["rows"]

    if kind == "scalar":
        return f"The {label}{scope} is {_fmt(result['scalar'])}."

    if kind == "describe":
        stats = {name: value for name, value in rows}
        return (f"{plan.measure.replace('_', ' ').capitalize()}{scope}: from {_fmt(stats['min'])} "
                f"to {_fmt(stats['max'])}, median {_fmt(stats['median'])}, "
                f"average {_fmt(stats['mean'])} across {stats['count']:,} values.")

    if kind == "trend":
        values = [(p, v) for p, v in rows if v is not None]
        first, last = values[0], values[-1]
        best = max(values, key=lambda item: item[1])
        worst = min(values, key=lambda item: item[1])
        text = (f"The {label}{scope} per {result['grain']} went from {_fmt(first[1])} in "
                f"{first[0]} to {_fmt(last[1])} in {last[0]}. The highest was {best[0]} "
                f"({_fmt(best[1])}) and the lowest was {worst[0]} ({_fmt(worst[1])}).")
        if result.get("partial_last_period"):
            text += " The latest period is incomplete, so compare it with care."
        return text

    top = rows[0]
    key, value = " / ".join(top[:-1]), top[-1]
    word = "highest" if plan.sort == "desc" else "lowest"
    text = f"{key} has the {word} {label}{scope}: {_fmt(value)}"
    total = result.get("total")
    if total and value is not None and total > 0 and plan.aggregation in ("sum", "count"):
        text += f" ({value / total * 100:.1f}% of the total)"
    text += "."
    if len(rows) > 1:
        text += f" Showing {len(rows)} of {result['row_count']} groups, {word} first."
    return text