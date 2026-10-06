from typing import Literal

from fastapi import APIRouter

from agents.profiling import profile_dataframe
from agents.quality import build_quality_report
from schemas import ProfileResponse, QualityResponse
from services import file_service

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("/{dataset_id}/profile", response_model=ProfileResponse)
def get_profile(dataset_id: str, version: Literal["clean", "raw"] = "clean"):
    if version == "raw":
        df = file_service.load_raw_dataset(dataset_id)
    else:
        df = file_service.load_clean_dataset(dataset_id)

    return ProfileResponse(
        dataset_id=dataset_id,
        version=version,
        profile=profile_dataframe(df),
    )


@router.get("/{dataset_id}/quality", response_model=QualityResponse)
def get_quality(dataset_id: str):
    raw_df = file_service.load_raw_dataset(dataset_id)
    clean_df = file_service.load_clean_dataset(dataset_id)
    cleaning_report = file_service.load_cleaning_report(dataset_id)

    quality = build_quality_report(
        profile_dataframe(raw_df),
        profile_dataframe(clean_df),
        cleaning_report,
    )
    return QualityResponse(dataset_id=dataset_id, quality=quality)