from typing import Any

import pandas as pd

from agents.drivers import analyze_drivers
from agents.profiling import _num as to_number, column_kind
from agents.query_plan import Filter, QueryPlan
from agents.trends import _grain, _is_partial_last, _period_labels
from agents.visualization import COLOR, _layout

MAX_TREND_POINTS = 200
MAX_CHART_BARS = 30
AGG_WORDS = {"sum": "total", "mean": "average", "median": "median", "min": "minimum", "max": "maximum"}


def label_for(plan: QueryPlan) -> str:
    name = plan.measure.replace("_", " ") if plan.measure else None
    if plan.aggregation == "count":
        return f"number of {name} values" if name else "number of rows"
    if plan.aggregation == "nunique":
        return f"number of distinct {name}"
    return f"{AGG_WORDS[plan.aggregation]} {name}"


# ---------- filters (boolean masks only, nothing is evaluated as code) ----------

def _coerce(series: pd.Series, value: Any) -> Any:
    kind = column_kind(series)
    if kind == "numeric":
        return float(value)
    if kind == "date":
        return pd.to_datetime(value)
    return str(value)


def _mask(df: pd.DataFrame, filters: list[Filter]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for f in filters:
        series = df[f.column]
        values = f.value if isinstance(f.value, list) else [f.value]
        if f.op in ("==", "!=", "in"):
            coerced = [_coerce(series, v) for v in values]
            target = series.astype(str) if column_kind(series) == "categorical" else series
            hit = target.isin(coerced)
            mask &= ~hit if f.op == "!=" else hit
        elif f.op == "contains":
            mask &= series.astype(str).str.contains(str(f.value), case=False, regex=False, na=False)
        else:
            value = _coerce(series, values[0])
            compare = {">": series.gt, ">=": series.ge, "<": series.lt, "<=": series.le}[f.op]
            mask &= compare(value)
    return mask


def _filter_focus(plan: QueryPlan) -> dict[str, Any]:
    return {f.column: f.value for f in plan.filters
            if f.op == "==" and not isinstance(f.value, list)}


# ---------- charts ----------

def _bar(title: str, x_title: str, y_title: str, labels: list, values: list) -> dict[str, Any]:
    figure = {
        "data": [{"type": "bar", "x": labels, "y": values, "marker": {"color": COLOR}}],
        "layout": _layout(title, x_title, y_title),
    }
    return {"type": "bar", "title": title, "figure": figure}


def _line(title: str, x_title: str, y_title: str, labels: list, values: list) -> dict[str, Any]:
    figure = {
        "data": [{"type": "scatter", "mode": "lines+markers", "x": labels, "y": values,
                  "line": {"color": COLOR}}],
        "layout": _layout(title, x_title, y_title),
    }
    return {"type": "line", "title": title, "figure": figure}


# ---------- operations ----------

def _scalar(plan: QueryPlan, data: pd.DataFrame) -> Any:
    if plan.aggregation == "count":
        return int(data[plan.measure].count()) if plan.measure else int(len(data))
    if plan.aggregation == "nunique":
        return int(data[plan.measure].nunique())
    return to_number(data[plan.measure].agg(plan.aggregation))


def _grouped(plan: QueryPlan, grouped) -> pd.Series:
    if plan.aggregation == "count":
        return grouped.size() if not plan.measure else grouped[plan.measure].count()
    return grouped[plan.measure].agg(plan.aggregation)


def _aggregate(plan: QueryPlan, data: pd.DataFrame, base: dict[str, Any]) -> dict[str, Any]:
    label = label_for(plan)
    if not plan.group_by:
        value = _scalar(plan, data)
        return {**base, "kind": "scalar", "label": label, "columns": [label], "rows": [[value]],
                "row_count": 1, "truncated": False, "scalar": value, "total": value,
                "chart": None, "focus": _filter_focus(plan)}

    values = _grouped(plan, data.groupby(plan.group_by, dropna=True))
    values = values.dropna().sort_values(ascending=(plan.sort == "asc"))
    limit = plan.limit or 10
    rows = []
    for key, value in values.head(limit).items():
        keys = key if isinstance(key, tuple) else (key,)
        rows.append([str(k) for k in keys] + [to_number(value)])

    total = _scalar(plan, data) if plan.aggregation in ("sum", "count") else None
    chart = None
    if len(plan.group_by) == 1 and 0 < len(rows) <= MAX_CHART_BARS:
        group = plan.group_by[0].replace("_", " ")
        chart = _bar(f"{label.capitalize()} by {group}", group.capitalize(), label,
                     [r[0] for r in rows], [r[1] for r in rows])
    focus = _filter_focus(plan)
    if rows:
        focus = {**focus, **dict(zip(plan.group_by, rows[0][:-1]))}

    return {**base, "kind": "table", "label": label, "columns": plan.group_by + [label],
            "rows": rows, "row_count": int(len(values)), "truncated": len(values) > limit,
            "scalar": None, "total": total, "chart": chart, "focus": focus}


def _trend(plan: QueryPlan, data: pd.DataFrame, base: dict[str, Any]) -> dict[str, Any]:
    column = plan.date_column
    dates = data[column].dropna()
    if dates.nunique() < 2:
        return {**base, "kind": "empty", "note": "There are not enough different dates to show a trend.",
                "rows": [], "focus": {}}

    grain = plan.time_grain or _grain(int((dates.max() - dates.min()).days))
    frame = data.assign(_period=_period_labels(data[column], grain))
    frame = frame[frame["_period"].notna()]
    values = _grouped(plan, frame.groupby("_period")).sort_index().tail(MAX_TREND_POINTS)
    rows = [[str(p), to_number(v)] for p, v in values.items()]
    label = label_for(plan)

    return {**base, "kind": "trend", "label": label, "grain": grain, "date_column": column,
            "columns": ["period", label], "rows": rows, "row_count": len(rows),
            "truncated": False, "scalar": None, "total": None,
            "partial_last_period": _is_partial_last(dates.max(), grain),
            "chart": _line(f"{label.capitalize()} per {grain}", grain.capitalize(), label,
                           [r[0] for r in rows], [r[1] for r in rows]),
            "focus": _filter_focus(plan)}


def _describe(plan: QueryPlan, data: pd.DataFrame, base: dict[str, Any]) -> dict[str, Any]:
    s = data[plan.measure].dropna()
    rows = [["count", int(len(s))], ["min", to_number(s.min())], ["median", to_number(s.median())],
            ["mean", to_number(s.mean())], ["max", to_number(s.max())], ["std", to_number(s.std())]]
    return {**base, "kind": "describe", "label": f"summary of {plan.measure.replace('_', ' ')}",
            "columns": ["statistic", "value"], "rows": rows, "row_count": len(rows),
            "truncated": False, "scalar": None, "total": None, "chart": None,
            "focus": _filter_focus(plan)}


def execute_plan(plan: QueryPlan, df: pd.DataFrame) -> dict[str, Any]:
    data = df[_mask(df, plan.filters)]
    base = {"matched_rows": int(len(data)), "total_rows": int(len(df))}
    if data.empty:
        return {**base, "kind": "empty", "rows": [], "focus": {}}
    if plan.operation == "change_drivers":
        return analyze_drivers(plan, data, base, label_for(plan), _filter_focus(plan))
    if plan.operation == "describe":
        return _describe(plan, data, base)
    if plan.operation == "trend":
        return _trend(plan, data, base)
    return _aggregate(plan, data, base)