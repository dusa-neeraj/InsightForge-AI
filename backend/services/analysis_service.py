from typing import Any

from agents.analysis import build_eda
from agents.insights import build_insights
from agents.kpis import build_kpis
from agents.narrator import build_facts, narrate
from agents.profiling import profile_dataframe
from agents.quality import build_quality_report
from services import file_service


def _compute(dataset_id: str):
    raw_df = file_service.load_raw_dataset(dataset_id)
    df = file_service.load_clean_dataset(dataset_id)
    cleaning_report = file_service.load_cleaning_report(dataset_id)

    eda = build_eda(df)
    kpis = build_kpis(df, eda)
    quality = build_quality_report(
        profile_dataframe(raw_df), profile_dataframe(df), cleaning_report
    )
    insights = build_insights(df, eda, kpis, quality)
    return eda, kpis, quality, insights


def calculated_insights(dataset_id: str) -> list[dict[str, Any]]:
    """The calculated insights only. No AI is involved, so this is free and fast."""
    cached = file_service.load_insights(dataset_id)
    if cached:
        return cached["insights"]
    return _compute(dataset_id)[3]


def get_insights(dataset_id: str, refresh: bool = False) -> dict[str, Any]:
    if not refresh:
        cached = file_service.load_insights(dataset_id)
        if cached:
            return {**cached, "cached": True}

    eda, kpis, quality, insights = _compute(dataset_id)
    narration = narrate(build_facts(eda, kpis, quality, insights), insights)

    payload = {"insights": insights, "narration": narration, "roles": kpis["roles"]}
    if narration["source"] == "ai":  # only cache the paid result
        file_service.save_insights(dataset_id, payload)
    return {**payload, "cached": False}