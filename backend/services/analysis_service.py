from typing import Any

from agents.analysis import build_eda
from agents.insights import build_insights
from agents.kpis import build_kpis
from agents.narrator import build_facts, narrate
from agents.profiling import profile_dataframe
from agents.quality import build_quality_report
from services import file_service


def get_insights(dataset_id: str, refresh: bool = False) -> dict[str, Any]:
    if not refresh:
        cached = file_service.load_insights(dataset_id)
        if cached:
            return {**cached, "cached": True}

    raw_df = file_service.load_raw_dataset(dataset_id)
    df = file_service.load_clean_dataset(dataset_id)
    cleaning_report = file_service.load_cleaning_report(dataset_id)

    eda = build_eda(df)
    kpis = build_kpis(df, eda)
    quality = build_quality_report(
        profile_dataframe(raw_df), profile_dataframe(df), cleaning_report
    )
    insights = build_insights(df, eda, kpis, quality)
    narration = narrate(build_facts(eda, kpis, quality, insights), insights)

    payload = {"insights": insights, "narration": narration, "roles": kpis["roles"]}
    if narration["source"] == "ai":  # only cache the paid result
        file_service.save_insights(dataset_id, payload)
    return {**payload, "cached": False}