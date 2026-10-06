import logging
import re
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from agents.analysis import _fmt
from agents.profiling import _num as to_number

logger = logging.getLogger(__name__)

COLOR = "#4f46e5"
ACCENT = "#f59e0b"
MAX_POINTS = 1000
MAX_HEATMAP_COLUMNS = 12
MAX_BAR_GROUPS = 12

MAX_LINES = 4
MAX_EFFECT_BARS = 2
MAX_CATEGORY_BARS = 3
MAX_HISTOGRAMS = 4
MAX_BOXES = 2
MAX_SCATTERS = 3


# ---------- small helpers ----------

def _label(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _slug(*parts: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")


def _floats(values) -> list[float | None]:
    return [to_number(v) for v in values]


def _sample(data: pd.DataFrame | pd.Series, n: int = MAX_POINTS):
    return data if len(data) <= n else data.sample(n, random_state=42)


def _layout(title: str, x_title: str | None = None, y_title: str | None = None, **extra: Any):
    layout: dict[str, Any] = {
        "title": {"text": title},
        "margin": {"l": 60, "r": 20, "t": 50, "b": 60},
        "showlegend": False,
    }
    if x_title:
        layout["xaxis"] = {"title": {"text": x_title}}
    if y_title:
        layout["yaxis"] = {"title": {"text": y_title}}
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(layout.get(key), dict):
            layout[key].update(value)
        else:
            layout[key] = value
    return layout


def _chart(chart_type, section, title, reason, columns, data, layout) -> dict[str, Any]:
    return {
        "id": _slug(chart_type, *columns),
        "type": chart_type,
        "section": section,
        "title": title,
        "reason": reason,
        "columns": columns,
        "figure": {"data": data, "layout": layout},
    }


# ---------- trends ----------

def _pick_metrics(trend: dict[str, Any]) -> list[dict[str, Any]]:
    def rank(metric: dict[str, Any]) -> int:
        trending = metric["direction"] in ("increasing", "decreasing")
        if trending and metric["name"] != "records":
            return 0
        return 1 if metric["name"] == "records" else 2

    return sorted(trend["metrics"], key=rank)[:3]


def _line(trend: dict[str, Any], metric: dict[str, Any]):
    points = metric["points"]
    periods = [p["period"] for p in points]
    values = [p["value"] for p in points]
    if sum(v is not None for v in values) < 3:
        return None

    grain, name = trend["grain"], metric["name"]
    readable = name.replace("_", " ")
    if name == "records":
        title, y_title = f"Records per {grain}", "Records"
    elif metric["aggregation"] == "mean":
        title, y_title = f"Average {readable} per {grain}", f"Average {readable}"
    else:
        title, y_title = f"Total {readable} per {grain}", f"Total {readable}"

    style = {"color": COLOR}
    if trend["partial_last_period"] and len(points) > 3:
        data = [
            {"type": "scatter", "mode": "lines+markers", "name": "Complete periods",
             "x": periods[:-1], "y": values[:-1], "line": style},
            {"type": "scatter", "mode": "lines+markers", "name": "Incomplete period",
             "x": periods[-2:], "y": values[-2:], "line": {"color": ACCENT, "dash": "dot"}},
        ]
        showlegend = True
    else:
        data = [{"type": "scatter", "mode": "lines+markers", "name": title,
                 "x": periods, "y": values, "line": style}]
        showlegend = False

    if metric["direction"] in ("increasing", "decreasing"):
        change = f" ({metric['change_pct']:+.1f}%)" if metric["change_pct"] is not None else ""
        reason = (f"{title.split(' per ')[0]} is {metric['direction']}{change} "
                  f"from {metric['first_period']} to {metric['last_period']}")
    else:
        reason = f"Tracks {readable if name != 'records' else 'the number of records'} over time"

    layout = _layout(title, f"{_label(trend['date_column'])} ({grain})", y_title,
                     showlegend=showlegend)
    return _chart("line", "trends", title, reason, [trend["date_column"], name], data, layout)


# ---------- comparisons and categories ----------

def _effect_bar(effect: dict[str, Any], df: pd.DataFrame):
    cat, measure = effect["category_column"], effect["measure"]
    data = df[[cat, measure]].dropna()
    stats = data.groupby(cat)[measure].agg(["count", "mean"])
    stats = stats[stats["count"] >= 3].sort_values("mean", ascending=False).head(MAX_BAR_GROUPS)
    if len(stats) < 2:
        return None

    means = _floats(stats["mean"])
    title = f"Average {measure.replace('_', ' ')} by {cat.replace('_', ' ')}"
    figure_data = [{
        "type": "bar",
        "x": [str(i) for i in stats.index],
        "y": means,
        "text": [_fmt(m) for m in means],
        "textposition": "auto",
        "marker": {"color": COLOR},
    }]
    layout = _layout(title, _label(cat), f"Average {measure.replace('_', ' ')}")
    return _chart("bar", "comparisons", title, effect["message"], [cat, measure],
                  figure_data, layout)


def _category_bar(col: dict[str, Any]):
    top = col["top_values"]
    if len(top) < 2:
        return None
    name, shown, total = col["name"], len(top), col["unique"]
    title = (f"{_label(name)}: top {shown} of {total}" if total > shown
             else f"{_label(name)} breakdown")
    reason = f"Shows how rows are split across '{name}'"
    if col["dominant"]:
        reason += f", dominated by '{top[0]['value']}' ({top[0]['pct']}%)"

    data = [{
        "type": "bar",
        "orientation": "h",
        "x": [t["count"] for t in top],
        "y": [t["value"] for t in top],
        "text": [f"{t['pct']}%" for t in top],
        "textposition": "auto",
        "marker": {"color": COLOR},
    }]
    layout = _layout(title, "Rows", _label(name), yaxis={"autorange": "reversed"},
                     margin={"l": 120})
    return _chart("bar", "categories", title, reason, [name], data, layout)


# ---------- distributions ----------

def _histogram(col: dict[str, Any]):
    edges, counts = col["histogram"]["edges"], col["histogram"]["counts"]
    if not counts or sum(counts) == 0:
        return None
    centers = [round((a + b) / 2, 4) for a, b in zip(edges[:-1], edges[1:])]
    widths = [round(b - a, 4) for a, b in zip(edges[:-1], edges[1:])]
    hover = [f"{_fmt(a)} to {_fmt(b)}" for a, b in zip(edges[:-1], edges[1:])]

    name = col["name"]
    title = f"Distribution of {name.replace('_', ' ')}"
    reason = f"Shows how '{name}' values are spread ({col['shape']})"
    data = [{
        "type": "bar", "x": centers, "y": counts, "width": widths,
        "hovertext": hover, "hoverinfo": "text+y", "marker": {"color": COLOR},
    }]
    layout = _layout(title, _label(name), "Count", bargap=0.05)
    return _chart("histogram", "distributions", title, reason, [name], data, layout)


def _box(col: dict[str, Any], df: pd.DataFrame):
    name = col["name"]
    values = _sample(df[name].dropna(), 3000)
    if len(values) < 5:
        return None
    title = f"Spread and outliers of {name.replace('_', ' ')}"
    reason = f"'{name}' has {col['outlier_pct']}% outliers, a box plot makes them visible"
    data = [{
        "type": "box", "y": _floats(values), "name": _label(name),
        "boxpoints": "outliers", "marker": {"color": COLOR},
    }]
    layout = _layout(title, None, _label(name))
    return _chart("box", "distributions", title, reason, [name], data, layout)


# ---------- relationships ----------

def _heatmap(correlations: dict[str, Any]):
    cols = correlations["columns"][:MAX_HEATMAP_COLUMNS]
    if len(cols) < 3 or not correlations["matrix"]:
        return None
    z = [row[: len(cols)] for row in correlations["matrix"][: len(cols)]]
    labels = [_label(c) for c in cols]
    data = [{
        "type": "heatmap", "x": labels, "y": labels, "z": z,
        "zmin": -1, "zmax": 1, "colorscale": "RdBu",
        "texttemplate": "%{z:.2f}", "hoverongaps": False,
    }]
    layout = _layout("Correlation matrix", yaxis={"autorange": "reversed"}, margin={"l": 110})
    reason = "Shows how every pair of numeric columns moves together (-1 to +1)"
    return _chart("heatmap", "relationships", "Correlation matrix", reason, cols, data, layout)


def _scatter(pair: dict[str, Any], df: pd.DataFrame):
    a, b = pair["column_a"], pair["column_b"]
    data = _sample(df[[a, b]].dropna())
    if len(data) < 5:
        return None
    x, y = data[a].to_numpy(dtype=float), data[b].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    x_min, x_max = float(x.min()), float(x.max())

    title = f"{_label(b)} vs {_label(a)}"
    reason = f"{pair['strength'].capitalize()} {pair['direction']} correlation (r = {pair['r']})"
    figure_data = [
        {"type": "scatter", "mode": "markers", "name": "Rows",
         "x": _floats(x), "y": _floats(y), "marker": {"color": COLOR, "opacity": 0.6}},
        {"type": "scatter", "mode": "lines", "name": "Trend line",
         "x": [round(x_min, 4), round(x_max, 4)],
         "y": [to_number(slope * x_min + intercept), to_number(slope * x_max + intercept)],
         "line": {"color": ACCENT}},
    ]
    layout = _layout(title, _label(a), _label(b), showlegend=True)
    return _chart("scatter", "relationships", title, reason, [a, b], figure_data, layout)


# ---------- main entry point ----------

def build_charts(df: pd.DataFrame, eda: dict[str, Any]) -> dict[str, Any]:
    charts: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    def add(chart_id: str, builder, *args: Any) -> None:
        try:
            chart = builder(*args)
        except Exception:
            logger.warning("Chart '%s' failed", chart_id, exc_info=True)
            skipped.append({"chart": chart_id, "reason": "could not be generated"})
            return
        if chart:
            charts.append(chart)

    # trends
    line_count = 0
    for trend in eda["time_trends"]:
        for metric in _pick_metrics(trend):
            if line_count >= MAX_LINES:
                break
            before = len(charts)
            add(f"line-{trend['date_column']}-{metric['name']}", _line, trend, metric)
            line_count += len(charts) - before

    # comparisons
    for effect in eda["category_effects"][:MAX_EFFECT_BARS]:
        add(f"bar-{effect['category_column']}-{effect['measure']}", _effect_bar, effect, df)

    # categories
    for col in eda["categorical"][:MAX_CATEGORY_BARS]:
        add(f"bar-{col['name']}", _category_bar, col)

    # distributions (skewed columns first)
    numeric = sorted(eda["numeric"], key=lambda c: 0 if "skewed" in c["shape"] else 1)
    for col in numeric[:MAX_HISTOGRAMS]:
        add(f"histogram-{col['name']}", _histogram, col)
    outlier_cols = [c for c in eda["numeric"] if (c["outlier_pct"] or 0) >= 5]
    for col in outlier_cols[:MAX_BOXES]:
        add(f"box-{col['name']}", _box, col, df)

    # relationships
    add("heatmap", _heatmap, eda["correlations"])
    for pair in eda["correlations"]["strong_pairs"][:MAX_SCATTERS]:
        add(f"scatter-{pair['column_a']}-{pair['column_b']}", _scatter, pair, df)

    return {
        "charts": charts,
        "skipped": skipped,
        "counts": dict(Counter(c["type"] for c in charts)),
    }