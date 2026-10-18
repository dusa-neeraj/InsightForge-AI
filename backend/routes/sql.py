from fastapi import APIRouter, Depends

from schemas import SqlRequest, SqlResponse, SqlSchemaResponse
from services import sql_service
from services.rate_limit import limit_sql

router = APIRouter(prefix="/datasets", tags=["SQL"], dependencies=[Depends(limit_sql)])


@router.post("/{dataset_id}/sql", response_model=SqlResponse)
def run_sql(dataset_id: str, request: SqlRequest):
    result = sql_service.run(dataset_id, request.question, request.sql)
    return SqlResponse(dataset_id=dataset_id, **result)


@router.get("/{dataset_id}/sql/schema", response_model=SqlSchemaResponse)
def sql_schema(dataset_id: str):
    return SqlSchemaResponse(dataset_id=dataset_id, **sql_service.schema(dataset_id))