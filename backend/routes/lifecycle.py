from fastapi import APIRouter

from services import cleanup

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str):
    cleanup.delete_dataset(dataset_id)
    return {"deleted": True}