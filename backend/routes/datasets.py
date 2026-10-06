from typing import Literal

from fastapi import APIRouter

from agents.profiling import profile_dataframe
from schemas import ProfileResponse
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