from pathlib import Path

import pandas as pd

from config import settings
from utils.errors import DatasetError
from utils.helpers import is_valid_dataset_id


def _dataset_dir(dataset_id: str) -> Path:
    if not is_valid_dataset_id(dataset_id):
        raise DatasetError("Invalid dataset ID.", 400)
    return settings.upload_dir / dataset_id


def save_dataset(
    dataset_id: str, raw_content: bytes, ext: str, clean_df: pd.DataFrame
) -> None:
    folder = _dataset_dir(dataset_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"raw{ext}").write_bytes(raw_content)
    clean_df.to_csv(folder / "clean.csv", index=False)


def load_clean_dataset(dataset_id: str) -> pd.DataFrame:
    path = _dataset_dir(dataset_id) / "clean.csv"
    if not path.exists():
        raise DatasetError("Dataset not found.", 404)
    return pd.read_csv(path)