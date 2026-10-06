from typing import Any

import numpy as np
import pandas as pd

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
TOP_N = 5


def _num(value: Any) -> int | float | None:
    """Convert numpy/pandas numbers to plain Python. NaN and inf become None."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    number = float(value)
    return None if np.isinf(number) else round(number, 4)


def column_kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "categorical"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    return "categorical"


def _profile_numeric(series: pd.Series) -> dict[str, Any]:
    values = series.dropna()
    if values.empty:
        return {}

    q = values.quantile(QUANTILES)
    q1, q3 = q[0.25], q[0.75]
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = int(((values < lower) | (values > upper)).sum())

    return {
        "min": _num(values.min()),
        "max": _num(values.max()),
        "mean": _num(values.mean()),
        "median": _num(values.median()),
        "std": _num(values.std()),
        "skewness": _num(values.skew()),
        "zeros": int((values == 0).sum()),
        "quantiles": {f"p{int(round(k * 100))}": _num(v) for k, v in q.items()},
        "outlier_count": outliers,
        "outlier_pct": round(outliers / len(values) * 100, 2),
        "outlier_bounds": {"lower": _num(lower), "upper": _num(upper)},
    }


def _profile_categorical(series: pd.Series) -> dict[str, Any]:
    values = series.dropna().astype(str)
    counts = values.value_counts()
    top = [
        {
            "value": str(value),
            "count": int(count),
            "pct": round(count / len(values) * 100, 2),
        }
        for value, count in counts.head(TOP_N).items()
    ]
    return {"top_values": top}


def _profile_date(series: pd.Series) -> dict[str, Any]:
    values = series.dropna()
    if values.empty:
        return {}
    first, last = values.min(), values.max()
    return {
        "min": first.isoformat(),
        "max": last.isoformat(),
        "span_days": int((last - first).days),
    }


def profile_column(series: pd.Series) -> dict[str, Any]:
    total = len(series)
    missing = int(series.isna().sum())
    non_null = total - missing
    unique = int(series.nunique(dropna=True))
    kind = column_kind(series)

    likely_id = (
        kind != "date"
        and not pd.api.types.is_float_dtype(series)
        and non_null >= 20
        and unique / non_null >= 0.95
    )

    info: dict[str, Any] = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "kind": kind,
        "missing": missing,
        "missing_pct": round(missing / total * 100, 2) if total else 0.0,
        "unique": unique,
        "cardinality_pct": round(unique / non_null * 100, 2) if non_null else 0.0,
        "likely_id": bool(likely_id),
    }

    if kind == "numeric":
        info.update(_profile_numeric(series))
    elif kind == "date":
        info.update(_profile_date(series))
    else:
        info.update(_profile_categorical(series))
    return info


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    rows, cols = df.shape
    columns = [profile_column(series) for _, series in df.items()]

    missing_cells = int(df.isna().sum().sum())
    total_cells = rows * cols
    duplicates = int(df.duplicated().sum())

    return {
        "overview": {
            "rows": rows,
            "columns": cols,
            "duplicate_rows": duplicates,
            "duplicate_pct": round(duplicates / rows * 100, 2) if rows else 0.0,
            "missing_cells": missing_cells,
            "missing_pct": (
                round(missing_cells / total_cells * 100, 2) if total_cells else 0.0
            ),
            "complete_rows": int((~df.isna().any(axis=1)).sum()),
            "memory_kb": round(df.memory_usage(deep=True).sum() / 1024, 1),
        },
        "column_types": {
            kind: [c["name"] for c in columns if c["kind"] == kind]
            for kind in ("numeric", "categorical", "date")
        }
        | {"likely_id": [c["name"] for c in columns if c["likely_id"]]},
        "columns": columns,
    }