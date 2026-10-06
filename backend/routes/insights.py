from fastapi import APIRouter

from schemas import InsightsResponse
from services import analysis_service

router = APIRouter(prefix="/datasets", tags=["Insights"])


@router.get("/{dataset_id}/insights", response_model=InsightsResponse)
def get_insights(dataset_id: str, refresh: bool = False):
    result = analysis_service.get_insights(dataset_id, refresh)
    return InsightsResponse(dataset_id=dataset_id, **result)