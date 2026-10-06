from typing import Any

import pandas as pd

from agents.analysis import _fmt
from agents.profiling import _num as to_number
from agents.trends import _aggregation

MAX_KPIS = 12
MAX_DIMENSIONS = 2
MIN_GROUP_SIZE = 3

MONEY_WORDS = {
    "revenue", "sales", "amount", "total", "profit", "income", "salary", "cost",
    "price", "spend", "expense", "fee", "budget", "pay", "wage", "charges",
}
PRIMARY_PRIORITY = [
    "revenue", "sales", "amount", "total", "profit", "income",
    "salary", "cost", "spend", "expense", "price",
]
QUANTITY_WORDS = {"quantity", "qty", "units", "volume", "orders", "count"}
DIMENSION_PRIORITY = [
    "product", "category", "department", "region", "city", "segment", "customer",
    "item", "type", "branch", "state", "country", "channel", "gender", "status",
]


# ---------- helpers ----------

def _tokens(name: str) -> set[str]:
    return set(name.split("_"))


def _text(name: str) -> str:
    return name.replace("_", " ")


def _kpi(
    kpi_id: str,
    label: str,
    value: Any,
    display: str,
    fmt: str,
    subtitle: str = "",
    category: str = "headline",
    columns: list[str] | None = None,
    delta_pct: float | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    return {
        "id": kpi_id,
        "label": label,
        "value": value,
        "display": display,
        "format": fmt,  # money | number | count | percent | text
        "subtitle": subtitle,
        "category": category,  # headline | breakdown | time | info
        "columns": columns or [],
        "delta_pct": delta_pct,
        "direction": direction,
    }


# ---------- role detection ----------

def _pick_primary(numeric: list[dict[str, Any]]) -> tuple[str | None, str | None, bool]:
    names = [c["name"] for c in numeric]
    for word in PRIMARY_PRIORITY:
        for name in names:
            if word in _tokens(name):
                return name, f"column name contains '{word}'", True
    if names:
        return names[0], "first numeric column (no business-like name found)", False
    return None, None, False


def _pick_secondary(numeric: list[dict[str, Any]], primary: str | None) -> str | None:
    for col in numeric:
        if col["name"] != primary and _tokens(col["name"]) & QUANTITY_WORDS:
            return col["name"]
    return None


def _pick_dimensions(categorical: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(col: dict[str, Any]) -> tuple[int, int]:
        tokens = _tokens(col["name"])
        for i, word in enumerate(DIMENSION_PRIORITY):
            if word in tokens:
                return i, col["unique"]
        return len(DIMENSION_PRIORITY), col["unique"]

    candidates = [c for c in categorical if 2 <= c["unique"] <= 30]
    return sorted(candidates, key=rank)[:MAX_DIMENSIONS]


# ---------- KPI builders ----------

def _measure_cards(col: dict[str, Any], df: pd.DataFrame, agg: str) -> list[dict[str, Any]]:
    name = col["name"]
    text = _text(name)
    series = df[name].dropna()
    if series.empty:
        return []

    fmt = "money" if _tokens(name) & MONEY_WORDS else "number"
    mean, median = to_number(series.mean()), to_number(series.median())
    note = f"Median: {_fmt(median)}"
    if "highly" in col["shape"]:
        note += ", the mean is pulled by extreme values"

    cards: list[dict[str, Any]] = []
    if agg == "sum":
        total = to_number(series.sum())
        cards.append(_kpi(f"total-{name}", f"Total {text}", total, _fmt(total), fmt,
                          f"Sum over {len(series):,} records", "headline", [name]))
        avg_label = f"Average {text} per record"
    else:
        avg_label = f"Average {text}"
    cards.append(_kpi(f"average-{name}", avg_label, mean, _fmt(mean), fmt, note,
                      "headline", [name]))
    return cards


def _dimension_card(
    dim: dict[str, Any], primary: str | None, agg: str, df: pd.DataFrame
) -> dict[str, Any] | None:
    name = dim["name"]
    if primary is None:
        top = dim["top_values"][0]
        return _kpi(f"top-{name}", f"Most common {_text(name)}", top["value"], top["value"],
                    "text", f"{top['pct']}% of records", "breakdown", [name])

    data = df[[name, primary]].dropna()
    if data.empty:
        return None
    stats = data.groupby(name)[primary].agg(["count", agg])
    if agg == "mean":  # averages of tiny groups are unreliable
        eligible = stats[stats["count"] >= MIN_GROUP_SIZE]
        if len(eligible) >= 2:
            stats = eligible
    stats = stats.sort_values(agg, ascending=False)
    if len(stats) < 2:
        return None

    best_group = str(stats.index[0])
    best_value = to_number(stats.iloc[0][agg])
    text = _text(primary)
    if agg == "sum":
        total = float(stats[agg].sum())
        share = f" ({best_value / total * 100:.1f}% of total)" if total > 0 and best_value else ""
        subtitle = f"Highest total {text}: {_fmt(best_value)}{share}"
    else:
        subtitle = f"Highest average {text}: {_fmt(best_value)}"
    return _kpi(f"top-{name}", f"Top {_text(name)}", best_group, best_group, "text",
                subtitle, "breakdown", [name, primary])


def _time_cards(
    trend: dict[str, Any], primary: str | None, df: pd.DataFrame
) -> list[dict[str, Any]]:
    metrics = {m["name"]: m for m in trend["metrics"]}
    metric = metrics.get(primary) or metrics["records"]
    name, grain = metric["name"], trend["grain"]
    label = "Records" if name == "records" else _text(name).capitalize()
    fmt = "count" if name == "records" else ("money" if _tokens(name) & MONEY_WORDS else "number")
    date_col = trend["date_column"]

    points = metric["points"]
    complete = points[:-1] if trend["partial_last_period"] and len(points) > 3 else points
    values = {p["period"]: p["value"] for p in points}
    cards: list[dict[str, Any]] = []

    best = metric["best_period"]
    if best and values.get(best) is not None:
        cards.append(_kpi("best-period", f"Best {grain}", best, best, "text",
                          f"{label}: {_fmt(values[best])}", "time", [date_col, name]))

    valid = [p for p in complete if p["value"] is not None]
    if len(valid) >= 2 and valid[-2]["value"]:
        prev, last = valid[-2], valid[-1]
        delta = to_number((last["value"] - prev["value"]) / abs(prev["value"]) * 100)
        direction = "up" if delta > 1 else "down" if delta < -1 else "flat"
        cards.append(_kpi(
            "latest-vs-previous", f"{label}, latest {grain} vs previous", delta,
            f"{delta:+.1f}%", "percent",
            f"{last['period']}: {_fmt(last['value'])} vs {prev['period']}: {_fmt(prev['value'])}",
            "time", [date_col, name], delta_pct=delta, direction=direction,
        ))

    dates = df[date_col].dropna()
    cards.append(_kpi(
        "period-covered", "Period covered", f"{dates.min().date()} to {dates.max().date()}",
        f"{dates.min().date()} to {dates.max().date()}", "text",
        f"{trend['span_days'] + 1:,} days, grouped by {grain}", "info", [date_col],
    ))
    return cards


# ---------- main entry point ----------

def build_kpis(df: pd.DataFrame, eda: dict[str, Any]) -> dict[str, Any]:
    numeric_by_name = {c["name"]: c for c in eda["numeric"]}
    primary, basis, business = _pick_primary(eda["numeric"])
    # without a business-like name we don't know if a column is additive, so average it
    agg = _aggregation(primary) if primary and business else "mean"
    secondary = _pick_secondary(eda["numeric"], primary)
    dimensions = _pick_dimensions(eda["categorical"])
    trend = eda["time_trends"][0] if eda["time_trends"] else None

    cards: list[dict[str, Any]] = [
        _kpi("total-records", "Total records", eda["overview"]["rows"],
             f"{eda['overview']['rows']:,}", "count",
             f"{eda['overview']['columns']} columns", "headline")
    ]
    if primary:
        cards += _measure_cards(numeric_by_name[primary], df, agg)
    if secondary:
        cards += _measure_cards(numeric_by_name[secondary], df, _aggregation(secondary))
    for dim in dimensions:
        card = _dimension_card(dim, primary, agg, df)
        if card:
            cards.append(card)
    if trend:
        cards += _time_cards(trend, primary if business else None, df)

    unique_cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in cards:
        if card["id"] not in seen:
            seen.add(card["id"])
            unique_cards.append(card)

    return {
        "cards": unique_cards[:MAX_KPIS],
        "roles": {
            "primary_measure": primary,
            "primary_basis": basis,
            "aggregation": agg if primary else None,
            "secondary_measure": secondary,
            "dimensions": [d["name"] for d in dimensions],
            "date_column": trend["date_column"] if trend else None,
        },
    }