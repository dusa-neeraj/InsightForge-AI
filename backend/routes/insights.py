from fastapi import APIRouter, Depends

from schemas import InsightsResponse
from services import analysis_service
from services.rate_limit import limit_insights

router = APIRouter(prefix="/datasets", tags=["Insights"], dependencies=[Depends(limit_insights)])


@router.get("/{dataset_id}/insights", response_model=InsightsResponse)
def get_insights(dataset_id: str, refresh: bool = False):
    result = analysis_service.get_insights(dataset_id, refresh)
    return InsightsResponse(dataset_id=dataset_id, **result)