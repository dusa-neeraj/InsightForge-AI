import logging
import shutil
import time
from pathlib import Path

from config import settings
from utils.errors import DatasetError
from utils.helpers import is_valid_dataset_id

logger = logging.getLogger(__name__)


def delete_dataset(dataset_id: str) -> None:
    """Deletes one dataset folder. Only valid 32-character ids can ever reach the file system."""
    if not is_valid_dataset_id(dataset_id):
        raise DatasetError("Invalid dataset ID.", 400)
    folder = settings.upload_dir / dataset_id
    if not folder.is_dir() or folder.is_symlink():
        raise DatasetError("Dataset not found.", 404)
    shutil.rmtree(folder)


def _uploaded_at(folder: Path) -> float:
    marker = folder / "clean.csv"
    return (marker if marker.exists() else folder).stat().st_mtime


def remove_expired(retention_hours: float | None = None, now: float | None = None) -> int:
    """Deletes datasets older than the retention time. Returns how many were removed."""
    hours = settings.retention_hours if retention_hours is None else retention_hours
    if hours <= 0 or not settings.upload_dir.exists():
        return 0
    cutoff = (time.time() if now is None else now) - hours * 3600
    removed = 0
    for folder in settings.upload_dir.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not is_valid_dataset_id(folder.name):
            continue  # never touch anything that is not a dataset folder
        try:
            if _uploaded_at(folder) < cutoff:
                shutil.rmtree(folder)
                removed += 1
        except OSError:
            logger.warning("Could not remove expired dataset %s", folder.name, exc_info=True)
    return removed