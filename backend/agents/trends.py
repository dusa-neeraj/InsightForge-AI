from typing import Any

import numpy as np
import pandas as pd

from agents.profiling import _num as to_number

MAX_MEASURES = 3
MIN_PERIODS = 3
FLAT_THRESHOLD = 0.1  # trend must change the metric by 10% of its mean to count
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MEAN_WORDS = {"price", "rate", "avg", "average", "mean", "score", "ratio",
              "pct", "percent", "age", "rating", "margin"}


def _grain(span_days: int) -> str:
    if span_days <= 45:
        return "day"
    if span_days <= 180:
        return "week"
    return "month"


def _period_labels(dates: pd.Series, grain: str) -> pd.Series:
    if grain == "day":
        return dates.dt.strftime("%Y-%m-%d")
    if grain == "week":  # weeks run Monday to Sunday, labelled by their Monday
        return dates.dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
    return dates.dt.strftime("%Y-%m")


def _is_partial_last(last: pd.Timestamp, grain: str) -> bool:
    if grain == "month":
        return bool(last.day != last.days_in_month)
    if grain == "week":
        return bool(last.dayofweek != 6)
    return False


def _aggregation(name: str) -> str:
    return "mean" if MEAN_WORDS & set(name.split("_")) else "sum"


def _describe(
    name: str, aggregation: str, periods: list[str], values: list[float], partial_last: bool
) -> dict[str, Any]:
    points = [{"period": p, "value": to_number(v)} for p, v in zip(periods, values)]

    # an unfinished last period would look like a fake drop, so leave it out of the math
    if partial_last and len(values) > MIN_PERIODS:
        periods, values = periods[:-1], values[:-1]
    pairs = [(p, v) for p, v in zip(periods, values) if not np.isnan(v)]

    result: dict[str, Any] = {
        "name": name,
        "aggregation": aggregation,
        "points": points,
        "direction": "unknown",
        "change_pct": None,
        "first_period": None,
        "last_period": None,
        "best_period": None,
        "worst_period": None,
    }
    if len(pairs) < MIN_PERIODS:
        return result

    labels = [p for p, _ in pairs]
    series = [v for _, v in pairs]
    first, last = series[0], series[-1]
    slope = float(np.polyfit(np.arange(len(series)), series, 1)[0])
    mean = float(np.mean(series))
    relative = slope * (len(series) - 1) / abs(mean) if mean else 0.0

    if abs(relative) < FLAT_THRESHOLD:
        direction = "flat"
    else:
        direction = "increasing" if slope > 0 else "decreasing"

    result.update(
        direction=direction,
        change_pct=round((last - first) / abs(first) * 100, 1) if first else None,
        first_period=labels[0],
        last_period=labels[-1],
        best_period=labels[int(np.argmax(series))],
        worst_period=labels[int(np.argmin(series))],
    )
    return result


def _weekday_pattern(dates: pd.Series, span_days: int) -> dict[str, Any] | None:
    if len(dates) < 20 or span_days < 28:
        return None
    counts = dates.dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
    peak = int(counts.idxmax())
    return {
        "metric": "records",
        "by_weekday": {WEEKDAYS[i]: int(counts.loc[i]) for i in range(7)},
        "peak_day": WEEKDAYS[peak],
        "peak_share_pct": round(float(counts.loc[peak]) / int(counts.sum()) * 100, 1),
    }


def build_time_trends(
    df: pd.DataFrame, date_columns: list[str], measure_columns: list[str]
) -> list[dict[str, Any]]:
    trends: list[dict[str, Any]] = []
    measures = measure_columns[:MAX_MEASURES]

    for date_col in date_columns[:2]:
        dates = df[date_col].dropna()
        if dates.nunique() < MIN_PERIODS:
            continue
        span_days = int((dates.max() - dates.min()).days)
        grain = _grain(span_days)

        labels = _period_labels(df[date_col], grain)
        mask = labels.notna()
        frame = df.loc[mask, measures].copy()
        frame["_period"] = labels[mask]
        grouped = frame.groupby("_period")

        records = grouped.size()
        periods = list(records.index)
        if len(periods) < MIN_PERIODS:
            continue

        partial = _is_partial_last(dates.max(), grain)
        series_list = [("records", "count", records)]
        for name in measures:
            aggregation = _aggregation(name)
            series_list.append((name, aggregation, grouped[name].agg(aggregation)))

        metrics = [
            _describe(name, agg, periods, [float(v) for v in s.reindex(periods)], partial)
            for name, agg, s in series_list
        ]
        trends.append(
            {
                "date_column": date_col,
                "grain": grain,
                "periods": len(periods),
                "span_days": span_days,
                "partial_last_period": partial,
                "metrics": metrics,
                "weekday_pattern": _weekday_pattern(dates, span_days),
            }
        )
    return trends