import logging
from typing import Any

import pandas as pd

from agents.analysis import _fmt
from agents.profiling import _num as to_number

logger = logging.getLogger(__name__)

MAX_INSIGHTS = 12
MIN_GROUP_SIZE = 3
IMPORTANCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _text(name: str) -> str:
    return name.replace("_", " ")


def _insight(kind: str, importance: str, message: str,
             evidence: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    return {"type": kind, "importance": importance, "message": message,
            "evidence": evidence, "columns": columns}


# ---------- composition: who contributes what ----------

def _share_insights(dim: str, primary: str, sums: pd.Series) -> list[dict[str, Any]]:
    total = float(sums.sum())
    if total <= 0 or (sums < 0).any() or len(sums) < 2:
        return []
    ranked = sums.sort_values(ascending=False)
    top_name, top_value = str(ranked.index[0]), float(ranked.iloc[0])
    share = top_value / total * 100

    found = [_insight(
        "composition", "high" if share >= 50 else "medium",
        f"'{top_name}' contributes {share:.1f}% of total {_text(primary)} across '{dim}' "
        f"({_fmt(to_number(top_value))} of {_fmt(to_number(total))})",
        {"group": top_name, "value": to_number(top_value), "total": to_number(total),
         "share_pct": round(share, 1), "groups": int(len(ranked))},
        [dim, primary],
    )]
    if len(ranked) >= 6:
        top3 = float(ranked.iloc[:3].sum()) / total * 100
        if top3 >= 80:
            found.append(_insight(
                "composition", "medium",
                f"The top 3 of {len(ranked)} '{dim}' groups make up {top3:.1f}% of total "
                f"{_text(primary)}",
                {"top3_share_pct": round(top3, 1), "groups": int(len(ranked))},
                [dim, primary],
            ))
    return found


def _gap_insights(dim: str, primary: str, stats: pd.DataFrame) -> list[dict[str, Any]]:
    eligible = stats[stats["count"] >= MIN_GROUP_SIZE]
    if len(eligible) < 2:
        return []
    means = eligible["mean"].sort_values(ascending=False)
    best, worst = str(means.index[0]), str(means.index[-1])
    high, low = float(means.iloc[0]), float(means.iloc[-1])
    if low == 0:
        return []
    gap = (high - low) / abs(low) * 100
    if gap < 5:
        return []
    return [_insight(
        "composition", "medium" if gap >= 20 else "low",
        f"'{best}' has the highest average {_text(primary)} across '{dim}' "
        f"({_fmt(to_number(high))}), {gap:.0f}% above '{worst}' ({_fmt(to_number(low))})",
        {"best_group": best, "best_mean": to_number(high), "worst_group": worst,
         "worst_mean": to_number(low), "gap_pct": round(gap, 1)},
        [dim, primary],
    )]


def _composition(df: pd.DataFrame, roles: dict[str, Any]) -> list[dict[str, Any]]:
    primary, agg = roles["primary_measure"], roles["aggregation"]
    if not primary:
        return []
    found: list[dict[str, Any]] = []
    for dim in roles["dimensions"]:
        data = df[[dim, primary]].dropna()
        if data.empty:
            continue
        stats = data.groupby(dim)[primary].agg(["count", agg])
        if agg == "sum":
            found += _share_insights(dim, primary, stats["sum"])
        else:
            found += _gap_insights(dim, primary, stats)
    return found


# ---------- trends over time ----------

def _metric_label(metric: dict[str, Any]) -> str:
    if metric["name"] == "records":
        return "The number of records"
    prefix = "Average" if metric["aggregation"] == "mean" else "Total"
    return f"{prefix} {_text(metric['name'])}"


def _trend(eda: dict[str, Any], roles: dict[str, Any]) -> list[dict[str, Any]]:
    if not eda["time_trends"]:
        return []
    trend = eda["time_trends"][0]
    metrics = {m["name"]: m for m in trend["metrics"]}
    primary = roles["primary_measure"] if roles["business_like"] else None
    metric = metrics.get(primary) or metrics["records"]
    label, grain = _metric_label(metric), trend["grain"]

    points = metric["points"]
    complete = points[:-1] if trend["partial_last_period"] and len(points) > 3 else points
    valid = [p for p in complete if p["value"] is not None]
    if len(valid) < 3:
        return []

    columns = [trend["date_column"], metric["name"]]
    first, last = valid[0], valid[-1]
    direction, change = metric["direction"], metric["change_pct"]
    found: list[dict[str, Any]] = []

    if direction in ("increasing", "decreasing"):
        pct = f"{change:+.1f}% " if change is not None else ""
        found.append(_insight(
            "trend", "high" if change is not None and abs(change) >= 25 else "medium",
            f"{label} is {direction} per {grain}: {pct}from {first['period']} "
            f"({_fmt(first['value'])}) to {last['period']} ({_fmt(last['value'])})",
            {"direction": direction, "change_pct": change,
             "first_period": first["period"], "first_value": first["value"],
             "last_period": last["period"], "last_value": last["value"],
             "periods": len(valid)},
            columns,
        ))
    elif direction == "flat":
        found.append(_insight(
            "trend", "low",
            f"{label} is stable per {grain}, with no clear upward or downward trend",
            {"direction": "flat", "periods": len(valid)}, columns,
        ))

    values = {p["period"]: p["value"] for p in valid}
    best, worst = metric["best_period"], metric["worst_period"]
    if len(valid) >= 4 and best in values and worst in values and best != worst:
        found.append(_insight(
            "trend", "low",
            f"Best {grain} for {label.lower()} was {best} ({_fmt(values[best])}); "
            f"the weakest was {worst} ({_fmt(values[worst])})",
            {"best_period": best, "best_value": values[best],
             "worst_period": worst, "worst_value": values[worst]},
            columns,
        ))

    if len(valid) >= 2 and valid[-2]["value"]:
        prev = valid[-2]
        delta = (last["value"] - prev["value"]) / abs(prev["value"]) * 100
        if abs(delta) >= 10:
            verb = "rose" if delta > 0 else "fell"
            found.append(_insight(
                "trend", "high" if abs(delta) >= 20 else "medium",
                f"{label} {verb} {abs(delta):.1f}% in the latest {grain} ({last['period']}) "
                f"versus the previous one ({prev['period']})",
                {"delta_pct": round(delta, 1), "latest_period": last["period"],
                 "latest_value": last["value"], "previous_period": prev["period"],
                 "previous_value": prev["value"]},
                columns,
            ))
    return found


# ---------- relationships, distributions, anomalies ----------

def _correlations(eda: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for p in eda["correlations"]["strong_pairs"][:2]:
        message = (f"'{p['column_a']}' and '{p['column_b']}' have a {p['strength']} "
                   f"{p['direction']} correlation (r = {p['r']})")
        if abs(p["r"]) >= 0.98:
            message += ", so they may carry the same information"
        found.append(_insight(
            "correlation", "high" if abs(p["r"]) >= 0.8 else "medium", message,
            {"r": p["r"], "strength": p["strength"]}, [p["column_a"], p["column_b"]],
        ))
    return found


def _effects(eda: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ("eta_squared", "best_group", "best_mean", "worst_group", "worst_mean", "sample_size")
    return [
        _insight("category_effect", "high" if e["eta_squared"] >= 0.3 else "medium",
                 e["message"], {k: e[k] for k in keys}, [e["category_column"], e["measure"]])
        for e in eda["category_effects"][:2]
    ]


def _outliers(eda: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for col in [c for c in eda["numeric"] if (c["outlier_pct"] or 0) >= 5][:2]:
        found.append(_insight(
            "outliers", "high" if col["outlier_pct"] >= 10 else "medium",
            f"'{col['name']}' has {col['outlier_count']} unusual value(s) "
            f"({col['outlier_pct']}% of rows); the maximum is {_fmt(col['max'])} "
            f"versus a median of {_fmt(col['median'])}",
            {"count": col["outlier_count"], "pct": col["outlier_pct"],
             "max": col["max"], "median": col["median"]},
            [col["name"]],
        ))
    return found


def _distribution(eda: dict[str, Any]) -> list[dict[str, Any]]:
    for col in eda["numeric"]:
        if "highly" in col["shape"] and col["mean"] is not None and col["median"] is not None:
            side = "above" if (col["skewness"] or 0) > 0 else "below"
            return [_insight(
                "distribution", "low",
                f"'{col['name']}' is {col['shape']}: the average ({_fmt(col['mean'])}) is well "
                f"{side} the typical value ({_fmt(col['median'])}), so a few extreme values pull it",
                {"mean": col["mean"], "median": col["median"], "skewness": col["skewness"]},
                [col["name"]],
            )]
    return []


def _dominant(eda: dict[str, Any]) -> list[dict[str, Any]]:
    for col in eda["categorical"]:
        if col["dominant"]:
            top = col["top_values"][0]
            return [_insight(
                "dominant_category", "low",
                f"'{col['name']}' is dominated by '{top['value']}' ({top['pct']}% of rows)",
                {"value": top["value"], "pct": top["pct"]}, [col["name"]],
            )]
    return []


# ---------- data quality and caution ----------

def _quality(quality: dict[str, Any]) -> list[dict[str, Any]]:
    before, after = quality["before"], quality["after"]
    message = f"Data quality score is {after['score']}/100 ({after['grade'].lower()})"
    if before["score"] != after["score"]:
        message += f", up from {before['score']} before cleaning"
    score = after["score"]
    found = [_insight(
        "quality", "high" if score < 50 else "medium" if score < 75 else "low", message,
        {"score_before": before["score"], "score_after": after["score"],
         "grade": after["grade"]}, [],
    )]

    issues = [i for i in quality["issues"] if i["severity"] in ("high", "medium")][:2]
    for issue in issues:
        found.append(_insight(
            "quality", issue["severity"], issue["message"],
            {"issue_type": issue["type"]}, [issue["column"]] if issue["column"] else [],
        ))

    for change in quality["changes"]:
        if change["type"] == "duplicates_removed" and before["rows"]:
            count = change["count"]
            found.append(_insight(
                "quality", "low",
                f"Cleaning removed {count} duplicate row(s) "
                f"({count / before['rows'] * 100:.1f}% of the original rows)",
                {"duplicates_removed": count, "original_rows": before["rows"]}, [],
            ))
    return found


def _caution(eda: dict[str, Any]) -> list[dict[str, Any]]:
    rows = eda["overview"]["rows"]
    if rows >= 30:
        return []
    return [_insight("caution", "medium",
                     f"The dataset has only {rows} rows, so patterns may be due to chance",
                     {"rows": rows}, [])]


# ---------- main entry point ----------

def build_insights(
    df: pd.DataFrame, eda: dict[str, Any], kpis: dict[str, Any], quality: dict[str, Any]
) -> list[dict[str, Any]]:
    roles = kpis["roles"]
    builders = [
        lambda: _composition(df, roles),
        lambda: _trend(eda, roles),
        lambda: _correlations(eda),
        lambda: _effects(eda),
        lambda: _outliers(eda),
        lambda: _distribution(eda),
        lambda: _dominant(eda),
        lambda: _caution(eda),
    ]
    found: list[dict[str, Any]] = []
    for builder in builders:
        try:
            found += builder()
        except Exception:
            logger.warning("An insight builder failed", exc_info=True)

    try:
        quality_found = _quality(quality)
    except Exception:
        logger.warning("The quality insight builder failed", exc_info=True)
        quality_found = []

    # The quality score always gets a slot, so users can see how far to trust the data.
    score, other_quality = quality_found[:1], quality_found[1:]
    found += other_quality
    found.sort(key=lambda item: IMPORTANCE_ORDER[item["importance"]])

    kept = found[: MAX_INSIGHTS - len(score)] + score
    kept.sort(key=lambda item: IMPORTANCE_ORDER[item["importance"]])
    return [{"id": f"I{n}", **item} for n, item in enumerate(kept, start=1)]