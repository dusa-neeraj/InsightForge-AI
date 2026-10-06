import re
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from agents.profiling import column_kind

Scalar = str | int | float | bool
NUMERIC_AGGS = {"sum", "mean", "median", "min", "max"}


class PlanError(Exception):
    """The plan cannot be run safely. The message is written for end users."""


class Filter(BaseModel):
    column: str
    op: Literal["==", "!=", ">", ">=", "<", "<=", "in", "contains"] = "=="
    value: Scalar | list[Scalar]


class QueryPlan(BaseModel):
    operation: Literal["aggregate", "trend", "describe", "unsupported"]
    measure: str | None = None
    aggregation: Literal["sum", "mean", "median", "min", "max", "count", "nunique"] = "sum"
    group_by: list[str] = Field(default_factory=list, max_length=2)
    filters: list[Filter] = Field(default_factory=list, max_length=5)
    sort: Literal["asc", "desc"] = "desc"
    limit: int | None = Field(default=None, ge=1, le=100)
    date_column: str | None = None
    time_grain: Literal["day", "week", "month"] | None = None
    reason: str | None = None


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text).lower())


def _resolve(name: str, df: pd.DataFrame) -> str:
    """Match a column name ignoring case, spaces and underscores."""
    key = _norm(name)
    for col in df.columns:
        if _norm(col) == key:
            return col
    shown = ", ".join(map(str, df.columns[:12]))
    raise PlanError(f"There is no column called '{name}'. Columns I can use: {shown}.")


def _check_filter(f: Filter, df: pd.DataFrame) -> Filter:
    col = _resolve(f.column, df)
    series = df[col]
    kind = column_kind(series)
    values = f.value if isinstance(f.value, list) else [f.value]

    if kind == "numeric":
        if f.op == "contains":
            raise PlanError(f"'{col}' is numeric, so 'contains' can't be used on it.")
        try:
            [float(v) for v in values]
        except (TypeError, ValueError):
            raise PlanError(f"'{col}' is numeric, but {values} is not a number.") from None
        return Filter(column=col, op=f.op, value=f.value)

    if kind == "date":
        if f.op in ("contains", "in"):
            raise PlanError(f"'{f.op}' can't be used on the date column '{col}'.")
        for v in values:
            if pd.isna(pd.to_datetime(v, errors="coerce")):
                raise PlanError(f"'{v}' is not a valid date for '{col}'.")
        return Filter(column=col, op=f.op, value=f.value)

    if f.op in (">", ">=", "<", "<="):
        raise PlanError(f"'{col}' is a text column, so '{f.op}' can't be used on it.")
    if f.op == "contains":
        return Filter(column=col, op="contains", value=str(values[0]))

    # text equality: values must exist in the data (matched ignoring case)
    lookup = {str(v).lower(): str(v) for v in series.dropna().unique()}
    resolved = []
    for v in values:
        key = str(v).strip().lower()
        if key not in lookup:
            examples = ", ".join(list(lookup.values())[:5])
            raise PlanError(f"'{v}' was not found in '{col}'. Some values are: {examples}.")
        resolved.append(lookup[key])
    return Filter(column=col, op=f.op, value=resolved if f.op == "in" else resolved[0])


def validate_plan(plan: QueryPlan, df: pd.DataFrame) -> QueryPlan:
    """Check a plan against the real dataset and return it with canonical names."""
    if plan.operation == "unsupported":
        raise PlanError(plan.reason or "That question can't be answered with this dataset.")

    measure = _resolve(plan.measure, df) if plan.measure else None
    if measure and plan.aggregation in NUMERIC_AGGS and column_kind(df[measure]) != "numeric":
        raise PlanError(
            f"'{measure}' is not a numeric column, so I can't calculate its {plan.aggregation}."
        )
    if plan.operation == "describe":
        if not measure or column_kind(df[measure]) != "numeric":
            raise PlanError("Tell me which numeric column to describe, for example: describe revenue.")
    elif not measure and plan.aggregation != "count":
        raise PlanError("Tell me which numeric column to calculate, for example: total revenue.")

    group_by: list[str] = []
    for name in plan.group_by:
        col = _resolve(name, df)
        if column_kind(df[col]) == "date":
            raise PlanError(f"'{col}' is a date column. Ask for a trend over time instead.")
        if col not in group_by:
            group_by.append(col)

    date_column = None
    if plan.operation == "trend":
        if plan.date_column:
            date_column = _resolve(plan.date_column, df)
        else:
            dates = [c for c in df.columns if column_kind(df[c]) == "date"]
            if not dates:
                raise PlanError("This dataset has no date column, so I can't show a trend over time.")
            date_column = dates[0]
        if column_kind(df[date_column]) != "date":
            raise PlanError(f"'{date_column}' is not a date column.")

    filters = [_check_filter(f, df) for f in plan.filters]
    limit = plan.limit if plan.limit else (10 if group_by else None)
    return plan.model_copy(
        update={
            "measure": measure,
            "group_by": group_by,
            "date_column": date_column,
            "filters": filters,
            "limit": limit,
        }
    )