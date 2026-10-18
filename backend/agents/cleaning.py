import logging
import re
import time
import warnings
from typing import Any

import numpy as np
import pandas as pd

from utils.errors import DatasetError


logger = logging.getLogger(__name__)

MAX_FILL_MISSING_PCT = 60.0
PARSE_RATIO = 0.9
MAX_CATEGORY_UNIQUE = 50

NULL_TOKENS = {
    "", "-", "--", "?", "n/a", "na", "nan",
    "none", "null", "nil", "missing",
}

DATE_NAME_HINTS = ("date", "time", "dob", "created", "updated")

STRICT_DATE_RE = re.compile(
    r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
)

YEAR_RE = re.compile(r"(?:19|20)\d{2}")

DAY_FIRST_RE = (
    r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}"
)

NUMBER_JUNK_RE = re.compile(r"[,\s₹$€£%]")
LEADING_ZERO_RE = re.compile(r"0\d+")

# A superset of characters used in ordinary numeric, scientific-notation,
# infinity/NaN, and complex-number strings accepted by numeric parsers.
# Values containing other characters cannot contribute to a successful
# pd.to_numeric conversion after NUMBER_JUNK_RE is applied.
NUMERIC_CANDIDATE_RE = r"[0-9eE.+\-infntyaj_]*"
PREFILTER_SAMPLE_SIZE = 512
PREFILTER_REJECT_RATIO = 0.5


# ---------- helpers ----------

def _is_text(series: pd.Series) -> bool:
    return not (
        pd.api.types.is_numeric_dtype(series)
        or pd.api.types.is_bool_dtype(series)
        or pd.api.types.is_datetime64_any_dtype(series)
    )


def _standardize_column_names(columns) -> list[str]:
    used: set[str] = set()
    names: list[str] = []

    for i, col in enumerate(columns):
        base = (
            re.sub(r"[\W_]+", "_", str(col).strip().lower())
            .strip("_")
            or f"column_{i + 1}"
        )

        name, n = base, 1

        while name in used:
            n += 1
            name = f"{base}_{n}"

        used.add(name)
        names.append(name)

    return names


def _normalize_text(value: Any) -> Any:
    """Normalize a single text value."""
    if pd.isna(value):
        return np.nan

    text = " ".join(str(value).split())
    return np.nan if text.casefold() in NULL_TOKENS else text


def _normalize_text_series(series: pd.Series) -> pd.Series:
    """Normalize text values with the same rules as _normalize_text."""
    # For object-backed columns, mapping the existing scalar normalizer avoids
    # running multiple Pandas string/regex passes over every column. This keeps
    # whitespace collapsing, case-insensitive null-token handling, and missing
    # value behavior in one place.
    return series.map(_normalize_text).astype(object)


def _sample_for_prefilter(series: pd.Series) -> pd.Series:
    """Return a deterministic, evenly spaced sample for cheap rejection tests."""
    if len(series) <= PREFILTER_SAMPLE_SIZE:
        return series
    positions = np.linspace(
        0, len(series) - 1, num=PREFILTER_SAMPLE_SIZE, dtype=np.int64
    )
    return series.iloc[positions]


def _try_numeric(
    series: pd.Series,
) -> tuple[pd.Series, int] | None:
    present = series.dropna()

    if present.empty:
        return None

    # Cheaply reject clearly textual columns before scanning every row with
    # several string operations. This is only a rejection prefilter; columns
    # that look plausibly numeric still go through the full-data checks below.
    sample = _sample_for_prefilter(present).astype("string")
    sample_candidates = sample.str.fullmatch(
        r"[0-9eE.+\-infntyaj_,\s₹$€£%]*",
        case=False,
        na=False,
    )
    if float(sample_candidates.mean()) < PREFILTER_REJECT_RATIO:
        return None

    # Candidate characters alone are not enough: date strings also contain
    # digits and hyphens. A small parse check rejects those before full scans.
    sample_stripped = sample.str.replace(NUMBER_JUNK_RE, "", regex=True)
    sample_converted = pd.to_numeric(sample_stripped, errors="coerce")
    sample_valid_ratio = float(sample_converted.notna().mean())
    if sample_valid_ratio < PREFILTER_REJECT_RATIO:
        return None

    present_strings = present.astype("string")
    starts_with_zero = present_strings.str.startswith("0", na=False)

    if starts_with_zero.any():
        leading_zero_values = present_strings[starts_with_zero]

        if leading_zero_values.str.fullmatch(LEADING_ZERO_RE).any():
            return None

    if series.notna().all():
        numeric_input = present_strings
    else:
        numeric_input = series.astype("string")

    # Reject clearly non-numeric columns before the expensive replace pass.
    # The candidate pattern also permits every character removed by
    # NUMBER_JUNK_RE, so a value accepted by the old post-replacement check
    # remains a candidate here. Candidate columns still use the same cleanup
    # and pd.to_numeric parser as before.
    candidate_pattern = r"[0-9eE.+\-infntyaj_,\s₹$€£%]*"
    candidate_mask = numeric_input.str.fullmatch(
        candidate_pattern,
        case=False,
        na=False,
    )
    candidate_count = int(candidate_mask.sum())

    if candidate_count / len(present) < PARSE_RATIO:
        return None

    stripped = numeric_input.str.replace(NUMBER_JUNK_RE, "", regex=True)
    converted = pd.to_numeric(stripped, errors="coerce")
    converted = converted.replace([np.inf, -np.inf], np.nan)

    valid = int(converted.notna().sum())

    if valid / len(present) < PARSE_RATIO:
        return None

    return converted, len(present) - valid


def _looks_day_first(present: pd.Series) -> bool:
    """Detect day-first dates when the values support that interpretation."""
    parts = present.str.extract(DAY_FIRST_RE)

    first = pd.to_numeric(parts[0], errors="coerce")
    second = pd.to_numeric(parts[1], errors="coerce")

    return bool((first > 12).any() and not (second > 12).any())


def _try_datetime(
    name: str,
    series: pd.Series,
) -> tuple[pd.Series, int, bool] | None:
    present_values = series.dropna()

    if present_values.empty:
        return None

    # Most ordinary text columns are not dates. Check a small, evenly spaced
    # sample before converting and regex-scanning every value in the column.
    sample = _sample_for_prefilter(present_values).astype(str)
    sample_strict_ratio = sample.str.match(STRICT_DATE_RE).mean()
    sample_hinted_ratio = 0.0
    if any(hint in name for hint in DATE_NAME_HINTS):
        sample_hinted_ratio = sample.str.contains(YEAR_RE, na=False).mean()

    if (
        sample_strict_ratio < PREFILTER_REJECT_RATIO
        and sample_hinted_ratio < PREFILTER_REJECT_RATIO
    ):
        return None

    present = present_values.astype(str)
    strict = present.str.match(STRICT_DATE_RE).mean() >= PARSE_RATIO

    hinted = False
    if any(hint in name for hint in DATE_NAME_HINTS):
        hinted = (
            present.str.contains(YEAR_RE, na=False).mean()
            >= PARSE_RATIO
        )

    if not (strict or hinted):
        return None

    day_first = _looks_day_first(present)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(
            series,
            errors="coerce",
            format="mixed",
            dayfirst=day_first,
        )

    if not pd.api.types.is_datetime64_any_dtype(parsed):
        return None

    valid = int(parsed.notna().sum())

    if valid / len(present) < PARSE_RATIO:
        return None

    return parsed, len(present) - valid, day_first


def _standardize_categories(
    series: pd.Series,
) -> tuple[pd.Series, dict[str, Any] | None]:
    """Merge spellings that differ only by capitalization."""
    values = series.dropna()

    if values.empty:
        return series, None

    unique = values.nunique()

    if unique > MAX_CATEGORY_UNIQUE and unique / len(values) > 0.5:
        return series, None

    groups: dict[str, list[tuple[str, int]]] = {}

    for spelling, count in values.value_counts().items():
        groups.setdefault(str(spelling).casefold(), []).append(
            (str(spelling), int(count))
        )

    mapping: dict[str, str] = {}
    merged: list[dict[str, Any]] = []

    for variants in groups.values():
        if len(variants) < 2:
            continue

        variants.sort(
            key=lambda item: (
                item[0].islower() or item[0].isupper(),
                -item[1],
                item[0],
            )
        )

        canonical = variants[0][0]
        others = [spelling for spelling, _ in variants[1:]]

        mapping.update({spelling: canonical for spelling in others})
        merged.append({
            "canonical": canonical,
            "variants": others,
        })

    if not mapping:
        return series, None

    changed = int(series.isin(list(mapping)).sum())

    info = {
        "cells_changed": changed,
        "merged": merged[:5],
    }

    return series.replace(mapping), info


# ---------- main entry point ----------

def clean_data(
    raw_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    started = time.perf_counter()

    def log_stage(stage: str) -> None:
        logger.info(
            "Cleaning stage=%s elapsed=%.2fs",
            stage,
            time.perf_counter() - started,
        )

    df = raw_df.copy()
    rows_before = len(df)

    log_stage("copy_completed")

    # 1. Standardize column names.
    new_names = _standardize_column_names(df.columns)

    columns_renamed = {
        str(old): new
        for old, new in zip(df.columns, new_names)
        if str(old) != new
    }

    df.columns = new_names

    # 2. Normalize text.
    placeholders: dict[str, int] = {}

    for col in df.columns:
        if not _is_text(df[col]):
            continue

        before = int(df[col].isna().sum())
        df[col] = _normalize_text_series(df[col])

        converted = int(df[col].isna().sum()) - before

        if converted > 0:
            placeholders[col] = converted

    log_stage("text_normalization_completed")

    # 3. Remove empty rows and columns.
    df = df.dropna(how="all")
    empty_rows_removed = rows_before - len(df)

    empty_columns = df.columns[df.isna().all(axis=0)].tolist()
    df = df.drop(columns=empty_columns)

    if df.empty or df.shape[1] == 0:
        raise DatasetError(
            "The dataset has no usable data after cleaning.",
            422,
        )

    log_stage("empty_data_cleanup_completed")

    # 4. Detect types and standardize categories.
    conversions: dict[str, dict[str, Any]] = {}
    standardized: dict[str, dict[str, Any]] = {}

    text_columns = [
        col for col in df.columns if _is_text(df[col])
    ]

    numeric_seconds = 0.0
    datetime_seconds = 0.0
    category_seconds = 0.0

    numeric_attempts = 0
    datetime_attempts = 0
    category_attempts = 0

    for col in text_columns:
        stage_started = time.perf_counter()
        numeric = _try_numeric(df[col])
        numeric_seconds += time.perf_counter() - stage_started
        numeric_attempts += 1

        if numeric is not None:
            df[col], invalid = numeric

            conversions[col] = {
                "to": "numeric",
                "invalid_set_missing": invalid,
            }
            continue

        stage_started = time.perf_counter()
        dates = _try_datetime(col, df[col])
        datetime_seconds += time.perf_counter() - stage_started
        datetime_attempts += 1

        if dates is not None:
            df[col], invalid, day_first = dates

            conversions[col] = {
                "to": "datetime",
                "invalid_set_missing": invalid,
                "day_first": day_first,
            }
            continue

        stage_started = time.perf_counter()
        df[col], info = _standardize_categories(df[col])
        category_seconds += time.perf_counter() - stage_started
        category_attempts += 1

        if info:
            standardized[col] = info

    logger.info(
        "Cleaning type_detection_details "
        "text_columns=%d numeric_attempts=%d numeric_seconds=%.2f "
        "datetime_attempts=%d datetime_seconds=%.2f "
        "category_attempts=%d category_seconds=%.2f",
        len(text_columns),
        numeric_attempts,
        numeric_seconds,
        datetime_attempts,
        datetime_seconds,
        category_attempts,
        category_seconds,
    )

    log_stage("type_detection_completed")

    # 5. Remove duplicate rows.
    # Compute the duplicate mask once; calling duplicated() and then
    # drop_duplicates() separately repeats the expensive full-frame hash pass.
    duplicate_mask = df.duplicated(keep="first")
    duplicates = int(duplicate_mask.sum())
    if duplicates:
        df = df.loc[~duplicate_mask].reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    if df.empty:
        raise DatasetError(
            "The dataset has no usable data after cleaning.",
            422,
        )

    log_stage("duplicate_removal_completed")

    # 6. Fill missing values where appropriate.
    missing_before = {
        col: int(count)
        for col, count in df.isna().sum().items()
        if count > 0
    }

    filled: dict[str, dict[str, Any]] = {}
    skipped_high: dict[str, float] = {}

    for col, count in missing_before.items():
        pct = count / len(df) * 100
        series = df[col]

        if pct > MAX_FILL_MISSING_PCT:
            skipped_high[col] = round(pct, 2)
            continue

        if pd.api.types.is_datetime64_any_dtype(series):
            continue

        if pd.api.types.is_numeric_dtype(series):
            df[col] = series.fillna(series.median())
            method = "median"
        else:
            mode = series.mode()
            fill_value = (
                mode.iloc[0] if not mode.empty else "unknown"
            )
            df[col] = series.fillna(fill_value)
            method = "most frequent value"

        filled[col] = {
            "count": count,
            "method": method,
        }

    log_stage("missing_value_filling_completed")

    # 7. Flag outliers using the IQR method. Never delete outliers.
    outliers: dict[str, int] = {}
    outlier_details: dict[str, dict[str, Any]] = {}

    numeric_columns = df.select_dtypes(include="number").columns

    for col in numeric_columns:
        values = df[col].dropna()

        if values.empty:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        flagged = values[(values < lower) | (values > upper)]

        if flagged.empty:
            continue

        outliers[col] = int(len(flagged))

        outlier_details[col] = {
            "count": int(len(flagged)),
            "pct": round(len(flagged) / len(values) * 100, 2),
            "lower_bound": round(float(lower), 4),
            "upper_bound": round(float(upper), 4),
            "lowest_outlier": float(flagged.min()),
            "highest_outlier": float(flagged.max()),
        }

    log_stage("outlier_detection_completed")

    # 8. Build the cleaning report.
    report: dict[str, Any] = {
        "rows_before": rows_before,
        "columns_renamed": columns_renamed,
        "placeholders_to_missing": placeholders,
        "empty_rows_removed": empty_rows_removed,
        "empty_columns_dropped": empty_columns,
        "type_conversions": conversions,
        "values_standardized": standardized,
        "duplicates_removed": duplicates,
        "missing_before": missing_before,
        "missing_filled": filled,
        "missing_skipped_high": skipped_high,
        "outliers_flagged": outliers,
        "outlier_details": outlier_details,
        "rows_after": len(df),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
    }

    log_stage("cleaning_finished")

    return df, report
