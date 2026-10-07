from typing import Any

import numpy as np
import pandas as pd

from agents.periods import previous_period
from agents.profiling import _is_identifier, _num as to_number, column_kind
from agents.query_plan import QueryPlan
from agents.trends import _is_partial_last, _period_labels
from agents.visualization import _layout
from utils.errors import PlanError

MAX_DIMENSIONS = 8
SHOWN_DIMENSIONS = 2
SHOWN_GROUPS = 6
MIN_ROWS = 10
FLAT_PCT = 1.0
UP, DOWN = "#16a34a", "#dc2626"


def _total(plan: QueryPlan, frame: pd.DataFrame) -> Any:
    if plan.aggregation == "count":
        return int(frame[plan.measure].count()) if plan.measure else int(len(frame))
    return to_number(frame[plan.measure].sum())


def _by_group(plan: QueryPlan, frame: pd.DataFrame, dim: str) -> pd.Series:
    grouped = frame.groupby(dim, dropna=True)
    if plan.aggregation == "count":
        return grouped.size() if not plan.measure else grouped[plan.measure].count()
    return grouped[plan.measure].sum()


def _dimensions(plan: QueryPlan, data: pd.DataFrame) -> list[str]:
    """Text columns that can explain a change. Identifiers and fixed filters are skipped."""
    fixed = {f.column for f in plan.filters if f.op in ("==", "in")}
    found = []
    for col in plan.group_by or list(data.columns):
        if col in fixed or col in (plan.date_column, plan.measure):
            continue
        series = data[col]
        if column_kind(series) != "categorical":
            continue
        unique, non_null = int(series.nunique()), int(series.notna().sum())
        if not 2 <= unique <= 30 or _is_identifier(col, series, "categorical", unique, non_null):
            continue
        found.append(col)
    return found[:MAX_DIMENSIONS]


def analyze_drivers(
    plan: QueryPlan, data: pd.DataFrame, base: dict[str, Any], label: str,
    filter_focus: dict[str, Any],
) -> dict[str, Any]:
    column, grain, target = plan.date_column, plan.time_grain, plan.period
    previous = previous_period(target, grain)

    frame = data.assign(_period=_period_labels(data[column], grain))
    current = frame[frame["_period"] == target]
    before = frame[frame["_period"] == previous]
    where = " for the selected filters" if plan.filters else ""
    if current.empty:
        raise PlanError(f"There is no data for {target}{where}.")
    if before.empty:
        raise PlanError(f"There is no data for {previous}{where}, so I can't compare {target} with it.")

    now, then = _total(plan, current), _total(plan, before)
    delta = now - then
    pct = round(delta / abs(then) * 100, 1) if then else None
    if delta == 0 or (pct is not None and abs(pct) < FLAT_PCT):
        direction = "flat"
    else:
        direction = "increase" if delta > 0 else "decrease"

    dimensions: list[dict[str, Any]] = []
    if direction != "flat":
        for dim in _dimensions(plan, data):
            table = pd.concat(
                [_by_group(plan, before, dim).rename("previous"),
                 _by_group(plan, current, dim).rename("current")],
                axis=1,
            ).fillna(0)
            table["change"] = table["current"] - table["previous"]
            table["share"] = table["change"] / delta * 100
            aligned = table[np.sign(table["change"]) == np.sign(delta)]
            if aligned.empty:
                continue
            ranked = table.loc[table["change"].abs().sort_values(ascending=False).index]
            dimensions.append({
                "column": dim,
                "explains_pct": round(float(aligned["share"].max()), 1),
                "contributors": [
                    {"group": str(group), "previous": to_number(row["previous"]),
                     "current": to_number(row["current"]), "change": to_number(row["change"]),
                     "share_pct": round(float(row["share"]), 1)}
                    for group, row in ranked.head(SHOWN_GROUPS).iterrows()
                ],
            })
        dimensions.sort(key=lambda d: -d["explains_pct"])
    dimensions = dimensions[:SHOWN_DIMENSIONS]

    dates = data[column].dropna()
    last_label = str(_period_labels(pd.Series([dates.max()]), grain).iloc[0])
    partial = target == last_label and _is_partial_last(dates.max(), grain)
    notes = []
    if partial:
        notes.append(f"{target} is not finished yet, so part of the change is simply "
                     f"because it has fewer days of data.")
    if len(current) < MIN_ROWS or len(before) < MIN_ROWS:
        notes.append(f"This is based on only {len(current)} rows in {target} and "
                     f"{len(before)} in {previous}, so treat it with caution.")
    notes.append("This shows where the change happened. The data alone cannot prove why it happened.")

    columns: list[str] = []
    rows: list[list[Any]] = []
    chart = None
    focus = dict(filter_focus)
    if dimensions:
        best = dimensions[0]
        columns = [best["column"], "previous", "current", "change", "share of change (%)"]
        rows = [[c["group"], c["previous"], c["current"], c["change"], c["share_pct"]]
                for c in best["contributors"]]
        title = f"Change in {label} by {best['column'].replace('_', ' ')}: {previous} to {target}"
        chart = {
            "type": "bar", "title": title,
            "figure": {
                "data": [{
                    "type": "bar",
                    "x": [c["group"] for c in best["contributors"]],
                    "y": [c["change"] for c in best["contributors"]],
                    "marker": {"color": [UP if c["change"] >= 0 else DOWN
                                         for c in best["contributors"]]},
                }],
                "layout": _layout(title, best["column"].replace("_", " ").capitalize(), "Change"),
            },
        }
        focus[best["column"]] = best["contributors"][0]["group"]

    return {
        **base, "kind": "drivers", "label": label, "grain": grain, "date_column": column,
        "target_period": target, "previous_period": previous,
        "target_value": now, "previous_value": then,
        "change": to_number(delta), "change_pct": pct, "direction": direction,
        "target_partial": partial, "dimensions": dimensions, "notes": notes,
        "columns": columns, "rows": rows, "row_count": len(rows), "truncated": False,
        "scalar": None, "total": None, "chart": chart, "focus": focus,
    }