import threading
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from agents.analysis import _fmt, build_eda
from agents.insights import build_insights
from agents.kpis import build_kpis
from agents.narrator import _rule_based, clean_text
from agents.profiling import column_kind, profile_dataframe
from agents.quality import build_quality_report
from agents.report_html import render_html
from agents.report_pdf import render_pdf
from agents.visualization import build_charts
from services import file_service
from utils.errors import DatasetError

MAX_CHARTS = 12
MAX_STAT_ROWS = 15
KEY_FINDINGS = 5
CURRENCIES = {"₹", "$", "€", "£"}
FORMULA_START = ("=", "+", "-", "@")
_slots = threading.BoundedSemaphore(2)  # report building is CPU-heavy, so only 2 at a time


# ---------- cleaned CSV ----------

def _safe_for_spreadsheets(df: pd.DataFrame) -> pd.DataFrame:
    """Text starting with = + - @ would run as a formula in Excel, so it gets a leading apostrophe."""
    out = df.copy()
    for col in out.columns:
        if column_kind(out[col]) == "categorical" and not pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].map(
                lambda v: "'" + v if isinstance(v, str) and v.startswith(FORMULA_START) else v
            )
    return out


def clean_csv_bytes(dataset_id: str) -> bytes:
    df = file_service.load_clean_dataset(dataset_id)
    return _safe_for_spreadsheets(df).to_csv(index=False).encode("utf-8-sig")  # BOM: Excel reads UTF-8


# ---------- report content ----------

def kpi_text(card: dict[str, Any], currency: str) -> str:
    value = card["value"]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if card["format"] == "money":
            return f"{currency}{_fmt(value)}"
        if card["format"] in ("count", "number"):
            return _fmt(value)
    return str(card["display"])


def _numeric_rows(eda: dict[str, Any]) -> list[list[str]]:
    return [
        [c["name"], _fmt(c["min"]), _fmt(c["mean"]), _fmt(c["median"]), _fmt(c["max"]),
         f"{c.get('outlier_count') or 0} ({c.get('outlier_pct') or 0}%)"]
        for c in eda["numeric"][:MAX_STAT_ROWS]
    ]


def _category_rows(eda: dict[str, Any]) -> list[list[str]]:
    rows = []
    for col in eda["categorical"][:MAX_STAT_ROWS]:
        top = col["top_values"][0] if col["top_values"] else None
        rows.append([col["name"], str(col["unique"]), f"{top['value']} ({top['pct']}%)" if top else "-"])
    return rows


def build_report_data(dataset_id: str, name: str, currency: str) -> dict[str, Any]:
    raw_df = file_service.load_raw_dataset(dataset_id)
    df = file_service.load_clean_dataset(dataset_id)
    cleaning_report = file_service.load_cleaning_report(dataset_id)

    profile = profile_dataframe(df)
    eda = build_eda(df)
    kpis = build_kpis(df, eda)
    quality = build_quality_report(profile_dataframe(raw_df), profile, cleaning_report)
    insights = build_insights(df, eda, kpis, quality)
    charts = build_charts(df, eda)["charts"][:MAX_CHARTS]

    cached = file_service.load_insights(dataset_id)  # the report never triggers a new AI call
    narration = cached["narration"] if cached else {**_rule_based(insights), "source": "rules", "model": None}

    dates = [c for c in profile["columns"] if c["kind"] == "date" and c.get("min")]
    date_range = None
    if dates:
        date_range = f"{min(c['min'] for c in dates)[:10]} to {max(c['max'] for c in dates)[:10]}"

    types = profile["column_types"]
    overview = profile["overview"]
    return {
        "title": name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "currency": currency,
        "overview": {
            "rows": overview["rows"], "columns": overview["columns"],
            "numeric": len(types["numeric"]), "categorical": len(types["categorical"]),
            "date": len(types["date"]), "missing_pct": overview["missing_pct"],
            "date_range": date_range,
        },
        "narration": narration,
        "key_findings": insights[:KEY_FINDINGS],
        "insights": insights,
        "kpis": [{"label": k["label"], "value": kpi_text(k, currency), "subtitle": k["subtitle"]}
                 for k in kpis["cards"]],
        "quality": quality,
        "changes": quality["changes"],
        "numeric_stats": {"headers": ["Column", "Min", "Mean", "Median", "Max", "Outliers"],
                          "rows": _numeric_rows(eda)},
        "category_stats": {"headers": ["Column", "Distinct values", "Most common"],
                           "rows": _category_rows(eda)},
        "charts": charts,
    }


def _build(dataset_id: str, name: str, currency: str, renderer):
    if not _slots.acquire(blocking=False):
        raise DatasetError("The server is busy building other reports. Please try again in a moment.", 429)
    try:
        title = clean_text(name, 80) or "Dataset"
        symbol = currency if currency in CURRENCIES else ""
        return renderer(build_report_data(dataset_id, title, symbol))
    finally:
        _slots.release()


def build_html(dataset_id: str, name: str, currency: str) -> str:
    return _build(dataset_id, name, currency, render_html)


def build_pdf(dataset_id: str, name: str, currency: str) -> bytes:
    return _build(dataset_id, name, currency, render_pdf)