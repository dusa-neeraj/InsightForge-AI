import io
import logging
import warnings
from typing import Any

import matplotlib
import numpy as np
from matplotlib.figure import Figure

matplotlib.rcParams["svg.fonttype"] = "none"  # keep text as text, which makes SVG files much smaller
warnings.filterwarnings("ignore", message="Glyph .* missing from font", category=UserWarning)

logger = logging.getLogger(__name__)

COLOR = "#4f46e5"
ACCENT = "#f59e0b"
LABEL_SIZE = 8
TICK_SIZE = 7
MAX_TICKS = 10
SUPPORTED = {"bar", "histogram", "line", "scatter", "box", "heatmap"}


def _axis_title(layout: dict[str, Any], axis: str) -> str:
    return ((layout.get(axis) or {}).get("title") or {}).get("text") or ""


def _numbers(values: list) -> list[float]:
    return [np.nan if v is None else v for v in values]


def _category_ticks(ax, labels: list) -> None:
    step = max(1, len(labels) // MAX_TICKS)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([str(v) for v in labels[::step]], rotation=35, ha="right", fontsize=TICK_SIZE)


def _draw_bar(ax, trace: dict[str, Any]) -> bool:
    """Draws bars. Returns True for horizontal bars."""
    x, y = trace["x"], trace["y"]
    color = (trace.get("marker") or {}).get("color", COLOR)
    if trace.get("orientation") == "h":
        ax.barh(range(len(y)), _numbers(x), color=color)
        ax.set_yticks(range(len(y)))
        ax.set_yticklabels([str(v) for v in y], fontsize=TICK_SIZE)
        ax.invert_yaxis()
        return True
    if x and isinstance(x[0], (int, float)):  # histogram bins
        ax.bar(x, _numbers(y), width=trace.get("width"), color=color, edgecolor="white")
    else:
        ax.bar(range(len(x)), _numbers(y), color=color)
        _category_ticks(ax, x)
    return False


def _plot_trace(ax, trace: dict[str, Any], xs: list, ys: list) -> None:
    mode = trace.get("mode", "")
    color = (trace.get("line") or {}).get("color") or (trace.get("marker") or {}).get("color") or COLOR
    label = trace.get("name")
    if "lines" in mode:
        dotted = (trace.get("line") or {}).get("dash") == "dot"
        ax.plot(xs, ys, color=color, linestyle=":" if dotted else "-",
                marker="o" if "markers" in mode else None, markersize=3, label=label)
    else:
        ax.scatter(xs, ys, s=10, alpha=0.6, color=color, label=label)


def _draw_lines(ax, traces: list[dict[str, Any]], legend: bool) -> None:
    categorical = bool(traces[0]["x"]) and isinstance(traces[0]["x"][0], str)
    if categorical:
        labels: list = []
        for trace in traces:
            for value in trace["x"]:
                if value not in labels:
                    labels.append(value)
        position = {value: i for i, value in enumerate(labels)}
        for trace in traces:
            _plot_trace(ax, trace, [position[v] for v in trace["x"]], _numbers(trace["y"]))
        _category_ticks(ax, labels)
    else:
        for trace in traces:
            _plot_trace(ax, trace, _numbers(trace["x"]), _numbers(trace["y"]))
    if legend:
        ax.legend(fontsize=TICK_SIZE, frameon=False)


def _draw_box(ax, trace: dict[str, Any]) -> None:
    values = [v for v in trace["y"] if v is not None]
    ax.boxplot(values, patch_artist=True, boxprops={"facecolor": "#e0e7ff"},
               medianprops={"color": COLOR}, flierprops={"markersize": 3})
    ax.set_xticks([])


def _draw_heatmap(fig, ax, trace: dict[str, Any]) -> None:
    z = np.array([[np.nan if v is None else v for v in row] for row in trace["z"]], dtype=float)
    image = ax.imshow(z, cmap="RdBu", vmin=-1, vmax=1)
    ax.set_xticks(range(len(trace["x"])))
    ax.set_xticklabels(trace["x"], rotation=40, ha="right", fontsize=TICK_SIZE)
    ax.set_yticks(range(len(trace["y"])))
    ax.set_yticklabels(trace["y"], fontsize=TICK_SIZE)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            if not np.isnan(z[i, j]):
                ax.text(j, i, f"{z[i, j]:.2f}", ha="center", va="center", fontsize=6)
    fig.colorbar(image, ax=ax, fraction=0.04)


def render_chart(chart: dict[str, Any], fmt: str) -> bytes | None:
    """Draws one dashboard chart spec as 'svg' or 'png'. Returns None if it can't be drawn."""
    figure = chart.get("figure") or {}
    data = figure.get("data") or []
    layout = figure.get("layout") or {}
    kind = chart.get("type")
    if not data or kind not in SUPPORTED:
        return None
    try:
        fig = Figure(figsize=(7.2, 4.6 if kind == "heatmap" else 3.6), layout="constrained")
        ax = fig.add_subplot()
        horizontal = False
        if kind in ("bar", "histogram"):
            horizontal = _draw_bar(ax, data[0])
        elif kind in ("line", "scatter"):
            _draw_lines(ax, data, bool(layout.get("showlegend")))
        elif kind == "box":
            _draw_box(ax, data[0])
        else:
            _draw_heatmap(fig, ax, data[0])

        if kind != "heatmap":
            ax.set_xlabel(_axis_title(layout, "xaxis"), fontsize=LABEL_SIZE)
            ax.set_ylabel(_axis_title(layout, "yaxis"), fontsize=LABEL_SIZE)
            ax.tick_params(labelsize=TICK_SIZE)
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="x" if horizontal else "y", alpha=0.25)
        ax.set_title(chart.get("title", ""), fontsize=9, loc="left")

        buffer = io.BytesIO()
        fig.savefig(buffer, format=fmt, dpi=150)
        return buffer.getvalue()
    except Exception:
        logger.warning("Could not draw chart %s", chart.get("id"), exc_info=True)
        return None