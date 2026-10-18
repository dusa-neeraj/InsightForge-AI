
import logging
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from agents.cleaning import clean_data
from config import settings
from schemas import UploadResponse
from services import file_service
from services.rate_limit import limit_uploads
from utils.errors import DatasetError
from utils.helpers import dataframe_preview, new_dataset_id, safe_filename
from utils.validators import read_dataframe_path, validate_upload_path

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Upload"])

CHUNK_SIZE = 1024 * 1024


@router.post(
    "/upload",
    response_model=UploadResponse,
    dependencies=[Depends(limit_uploads)],
)
async def upload(file: UploadFile = File(...)):
    started = time.perf_counter()
    temp_path = None

    def log_stage(stage):
        logger.info(
            "Upload stage=%s elapsed=%.2fs",
            stage,
            time.perf_counter() - started,
        )

    try:
        suffix = Path(file.filename or "").suffix.lower()
        temp_file = tempfile.NamedTemporaryFile(
            prefix="ai_data_upload_",
            suffix=suffix,
            delete=False,
        )
        temp_path = Path(temp_file.name)
        total_bytes = 0

        try:
            with temp_file:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    total_bytes += len(chunk)

                    if total_bytes > settings.max_upload_bytes:
                        raise DatasetError(
                            f"File is too large. Maximum size is "
                            f"{settings.max_upload_mb} MB.",
                            413,
                        )

                    temp_file.write(chunk)
        finally:
            await file.close()

        log_stage(f"file_received bytes={total_bytes}")

        ext = await run_in_threadpool(
            validate_upload_path,
            file.filename,
            temp_path,
        )
        log_stage("file_validated")

        df = await run_in_threadpool(
            read_dataframe_path,
            temp_path,
            ext,
        )
        log_stage(
            f"dataframe_loaded rows={len(df)} columns={len(df.columns)}"
        )

        try:
            clean_df, report = await run_in_threadpool(
                clean_data,
                df,
            )
        except DatasetError:
            raise
        except Exception:
            logger.exception("Cleaning failed")
            raise DatasetError(
                "Cleaning failed for this dataset.",
                500,
            )

        log_stage(
            f"cleaning_completed rows={len(clean_df)} "
            f"columns={len(clean_df.columns)}"
        )

        dataset_id = new_dataset_id()

        await run_in_threadpool(
            file_service.save_dataset_from_path,
            dataset_id,
            temp_path,
            ext,
            clean_df,
            report,
        )
        log_stage("dataset_saved")

        preview = await run_in_threadpool(
            dataframe_preview,
            clean_df,
        )
        log_stage("preview_created")

        response = UploadResponse(
            dataset_id=dataset_id,
            filename=safe_filename(file.filename),
            report=report,
            preview=preview,
        )
        log_stage("response_ready")

        return response

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
