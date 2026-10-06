import logging

from fastapi import APIRouter, File, UploadFile

from agents.cleaning import clean_data
from config import settings
from schemas import UploadResponse
from services import file_service
from utils.errors import DatasetError
from utils.helpers import dataframe_preview, new_dataset_id, safe_filename
from utils.validators import read_dataframe, validate_upload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    # read one byte more than the limit so we can detect oversized files
    content = await file.read(settings.max_upload_bytes + 1)
    ext = validate_upload(file.filename, content)
    df = read_dataframe(content, ext)
    try:
        clean_df, report = clean_data(df)
    except DatasetError:
        raise
    except Exception:
        logger.exception("Cleaning failed")
        raise DatasetError("Cleaning failed for this dataset.", 500)

    dataset_id = new_dataset_id()
    file_service.save_dataset(dataset_id, content, ext, clean_df, report)

    return UploadResponse(
        dataset_id=dataset_id,
        filename=safe_filename(file.filename),
        report=report,
        preview=dataframe_preview(clean_df),
    )