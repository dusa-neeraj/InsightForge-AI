import io
import logging
from pathlib import Path

import pandas as pd

from config import settings
from utils.errors import DatasetError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def validate_upload(filename: str | None, content: bytes) -> str:
    """Check type, emptiness and size. Returns the file extension."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DatasetError("Only .csv and .xlsx files are supported.", 400)
    if len(content) == 0:
        raise DatasetError("The uploaded file is empty.", 400)
    if len(content) > settings.max_upload_bytes:
        raise DatasetError(
            f"File is too large. Maximum size is {settings.max_upload_mb} MB.", 413
        )
    return ext


def read_dataframe(content: bytes, ext: str) -> pd.DataFrame:
    """Read CSV/XLSX bytes into a DataFrame with friendly errors."""
    try:
        if ext == ".csv":
            try:
                df = pd.read_csv(io.BytesIO(content))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), encoding="latin-1")
        else:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except pd.errors.EmptyDataError:
        raise DatasetError("The file contains no data.", 400)
    except Exception:
        logger.warning("Failed to read uploaded file", exc_info=True)
        raise DatasetError(
            "Could not read the file. It may be corrupted or badly formatted.", 400
        )

    if df.shape[1] == 0 or df.empty:
        raise DatasetError("The dataset has no rows to analyze.", 422)
    return df