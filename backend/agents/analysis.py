from typing import Any

import numpy as np
import pandas as pd

from agents.profiling import _num as to_number, profile_dataframe
from agents.trends import build_time_trends

MAX_CATEGORIES = 100
TOP_VALUES = 10
HISTOGRAM_BINS = 10
MAX_CORR_COLUMNS = 30
MAX_EFFECT_COLUMNS = 8
MAX_EFFECT_GROUPS = 20
STRONG_R = 0.5
MIN_ETA = 0.1
DOMINANT_PCT = 60.0
MAX_RELATIONSHIPS = 12

NUMERIC_KEYS = ("name", "min", "max", "mean", "median", "std", "skewness",
                "missing_pct", "outlier_count", "outlier_pct", "quantiles")


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _shape(skew: float | None) -> str:
    if skew is None:
        return "unknown"
    if abs(skew) < 0.5:
        return "roughly symmetric"
    side = "right" if skew > 0 else "left"
    return f"{'highly' if abs(skew) >= 1 else 'moderately'} {side}-skewed"


def _numeric_summary(col: dict[str, Any], series: pd.Series) -> dict[str, Any]:
    summary = {key: col.get(key) for key in NUMERIC_KEYS}
    summary["shape"] = _shape(col.get("skewness"))

    values = series.dropna()
    values = values[np.isfinite(values)]
    if values.empty:
        summary["histogram"] = {"edges": [], "counts": []}
    else:
        counts, edges = np.histogram(values, bins=HISTOGRAM_BINS)
        summary["histogram"] = {
            "edges": [round(float(e), 4) for e in edges],
            "counts": [int(c) for c in counts],
        }
    return summary


def _categorical_summary(col: dict[str, Any], series: pd.Series) -> dict[str, Any]:
    values = series.dropna().astype(str)
    total = len(values)
    top = [
        {"value": str(v), "count": int(c), "pct": round(c / total * 100, 2)}
        for v, c in values.value_counts().head(TOP_VALUES).items()
    ]
    top_share = top[0]["pct"] if top else 0.0
    return {
        "name": col["name"],
        "unique": col["unique"],
        "missing_pct": col["missing_pct"],
        "top_values": top,
        "top_share_pct": top_share,
        "dominant": bool(top_share >= DOMINANT_PCT and col["unique"] > 1),
    }


def _strength(r_abs: float) -> str:
    if r_abs >= 0.8:
        return "very strong"
    return "strong" if r_abs >= 0.6 else "moderate"


def _correlations(df: pd.DataFrame, names: list[str]) -> dict[str, Any]:
    names = names[:MAX_CORR_COLUMNS]
    if len(names) < 2 or len(df) < 5:
        return {"method": "pearson", "columns": names, "matrix": [], "strong_pairs": []}

    corr = df[names].corr(numeric_only=True)
    matrix = [[to_number(corr.loc[a, b]) for b in names] for a in names]

    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = corr.loc[a, b]
            if pd.isna(r) or abs(r) < STRONG_R:
                continue
            pairs.append(
                {
                    "column_a": a,
                    "column_b": b,
                    "r": round(float(r), 3),
                    "strength": _strength(abs(float(r))),
                    "direction": "positive" if r > 0 else "negative",
                }
            )
    pairs.sort(key=lambda p: -abs(p["r"]))
    return {"method": "pearson", "columns": names, "matrix": matrix, "strong_pairs": pairs[:10]}


def _category_effects(
    df: pd.DataFrame, numeric: list[dict[str, Any]], categorical: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Which categorical column explains the most variation in which number (eta-squared)."""
    effects: list[dict[str, Any]] = []
    for num in numeric[:MAX_EFFECT_COLUMNS]:
        for cat in categorical[:MAX_EFFECT_COLUMNS]:
            if cat["unique"] > MAX_EFFECT_GROUPS:
                continue
            data = df[[cat["name"], num["name"]]].dropna()
            if len(data) < 10:
                continue
            stats = data.groupby(cat["name"])[num["name"]].agg(["count", "mean"])
            stats = stats[stats["count"] >= 3]
            if len(stats) < 2:
                continue

            kept = data[data[cat["name"]].isin(stats.index)][num["name"]]
            grand = kept.mean()
            ss_total = ((kept - grand) ** 2).sum()
            if ss_total == 0:
                continue
            eta = float((stats["count"] * (stats["mean"] - grand) ** 2).sum() / ss_total)
            if eta < MIN_ETA:
                continue

            best, worst = stats["mean"].idxmax(), stats["mean"].idxmin()
            best_mean, worst_mean = to_number(stats["mean"].max()), to_number(stats["mean"].min())
            effects.append(
                {
                    "category_column": cat["name"],
                    "measure": num["name"],
                    "eta_squared": round(eta, 3),
                    "groups_compared": int(len(stats)),
                    "sample_size": int(len(kept)),
                    "best_group": str(best),
                    "best_mean": best_mean,
                    "worst_group": str(worst),
                    "worst_mean": worst_mean,
                    "message": (
                        f"'{cat['name']}' explains about {eta:.0%} of the variation in "
                        f"'{num['name']}': '{best}' has the highest average ({_fmt(best_mean)}) "
                        f"and '{worst}' the lowest ({_fmt(worst_mean)})"
                    ),
                }
            )
    effects.sort(key=lambda e: -e["eta_squared"])
    return effects[:8]


def _relationships(
    numeric: list[dict[str, Any]],
    categorical: list[dict[str, Any]],
    correlations: dict[str, Any],
    effects: list[dict[str, Any]],
    trends: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for p in correlations["strong_pairs"][:3]:
        message = (f"'{p['column_a']}' and '{p['column_b']}' have a {p['strength']} "
                   f"{p['direction']} correlation (r = {p['r']})")
        if abs(p["r"]) >= 0.98:
            message += ", they may carry the same information"
        items.append({"type": "correlation", "columns": [p["column_a"], p["column_b"]],
                      "message": message})

    for e in effects[:3]:
        items.append({"type": "category_effect",
                      "columns": [e["category_column"], e["measure"]], "message": e["message"]})

    trend_items = 0
    for t in trends:
        metrics = [m for m in t["metrics"] if m["name"] != "records"]
        metrics += [m for m in t["metrics"] if m["name"] == "records"]
        for m in metrics:
            if m["direction"] not in ("increasing", "decreasing") or trend_items >= 3:
                continue
            label = "the number of records" if m["name"] == "records" else f"'{m['name']}'"
            change = f" ({m['change_pct']:+.1f}%)" if m["change_pct"] is not None else ""
            items.append({
                "type": "trend", "columns": [t["date_column"], m["name"]],
                "message": (f"{label} is {m['direction']} per {t['grain']}{change} "
                            f"from {m['first_period']} to {m['last_period']}"),
            })
            trend_items += 1

    skewed = [c for c in numeric if "highly" in c["shape"] and c["mean"] is not None
              and c["median"] is not None]
    for c in skewed[:2]:
        side = "above" if (c["skewness"] or 0) > 0 else "below"
        items.append({
            "type": "distribution", "columns": [c["name"]],
            "message": (f"'{c['name']}' is {c['shape']}: the mean ({_fmt(c['mean'])}) is well "
                        f"{side} the median ({_fmt(c['median'])}), so a few extreme values pull it"),
        })

    for c in [c for c in numeric if (c["outlier_pct"] or 0) >= 5][:2]:
        items.append({"type": "outliers", "columns": [c["name"]],
                      "message": f"'{c['name']}' has {c['outlier_pct']}% outliers, worth checking"})

    for c in [c for c in categorical if c["dominant"]][:2]:
        top = c["top_values"][0]
        items.append({"type": "dominant_category", "columns": [c["name"]],
                      "message": f"'{c['name']}' is dominated by '{top['value']}' ({top['pct']}% of rows)"})

    return items[:MAX_RELATIONSHIPS]


def build_eda(df: pd.DataFrame) -> dict[str, Any]:
    profile = profile_dataframe(df)

    numeric: list[dict[str, Any]] = []
    categorical: list[dict[str, Any]] = []
    dates: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    for col in profile["columns"]:
        if col["kind"] == "date":
            if col["unique"] > 1:
                dates.append(col)
            continue
        if col["likely_id"]:
            excluded.append({"name": col["name"], "reason": "identifier"})
        elif col["unique"] <= 1:
            excluded.append({"name": col["name"], "reason": "constant or empty"})
        elif col["kind"] == "numeric":
            numeric.append(col)
        elif col["unique"] <= MAX_CATEGORIES:
            categorical.append(col)
        else:
            excluded.append({"name": col["name"], "reason": "too many distinct values"})

    numeric_names = [c["name"] for c in numeric]
    numeric_out = [_numeric_summary(c, df[c["name"]]) for c in numeric]
    categorical_out = [_categorical_summary(c, df[c["name"]]) for c in categorical]
    correlations = _correlations(df, numeric_names)
    effects = _category_effects(df, numeric, categorical)
    trends = build_time_trends(df, [c["name"] for c in dates], numeric_names)

    notes = [
        "Correlation shows that two columns move together, not that one causes the other.",
        "Category effects show the share of variation explained, treat small samples carefully.",
    ]
    if len(df) < 30:
        notes.append(f"The dataset has only {len(df)} rows, so patterns may be due to chance.")

    return {
        "overview": {
            "rows": len(df),
            "columns": df.shape[1],
            "numeric_columns": len(numeric),
            "categorical_columns": len(categorical),
            "date_columns": len(dates),
            "excluded_columns": len(excluded),
        },
        "numeric": numeric_out,
        "categorical": categorical_out,
        "correlations": correlations,
        "category_effects": effects,
        "time_trends": trends,
        "relationships": _relationships(numeric_out, categorical_out, correlations, effects, trends),
        "excluded_columns": excluded,
        "notes": notes,
    }