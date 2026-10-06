import re
import warnings
from typing import Any

import numpy as np
import pandas as pd

from utils.errors import DatasetError

MAX_FILL_MISSING_PCT = 60.0  # columns with more missing than this are not filled
PARSE_RATIO = 0.9  # share of values that must parse before a column is converted
MAX_CATEGORY_UNIQUE = 50  # only standardize spellings in low-cardinality columns

NULL_TOKENS = {"", "-", "--", "?", "n/a", "na", "nan", "none", "null", "nil", "missing"}
DATE_NAME_HINTS = ("date", "time", "dob", "created", "updated")
STRICT_DATE_RE = re.compile(
    r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
)
YEAR_RE = re.compile(r"(19|20)\d{2}")
DAY_FIRST_RE = r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}"
NUMBER_JUNK_RE = re.compile(r"[,\s₹$€£%]")
LEADING_ZERO_RE = re.compile(r"0\d+")


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
        base = re.sub(r"[\W_]+", "_", str(col).strip().lower()).strip("_") or f"column_{i + 1}"
        name, n = base, 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        used.add(name)
        names.append(name)
    return names


def _normalize_text(value: Any) -> Any:
    """Trim, collapse spaces, and turn placeholder text into a real missing value."""
    if pd.isna(value):
        return np.nan
    text = " ".join(str(value).split())
    return np.nan if text.casefold() in NULL_TOKENS else text


def _try_numeric(series: pd.Series) -> tuple[pd.Series, int] | None:
    present = series.dropna()
    if present.empty:
        return None
    # "01234" style values are identifiers (zip codes, codes), keep them as text
    if present.map(lambda v: bool(LEADING_ZERO_RE.fullmatch(str(v)))).any():
        return None
    stripped = series.map(lambda v: v if pd.isna(v) else NUMBER_JUNK_RE.sub("", str(v)))
    converted = pd.to_numeric(stripped, errors="coerce")
    converted = converted.replace([np.inf, -np.inf], np.nan)
    valid = int(converted.notna().sum())
    if valid / len(present) < PARSE_RATIO:
        return None
    return converted, len(present) - valid


def _looks_day_first(present: pd.Series) -> bool:
    """True for DD/MM/YYYY data: some first part is above 12 and no second part is."""
    parts = present.str.extract(DAY_FIRST_RE)
    first = pd.to_numeric(parts[0], errors="coerce")
    second = pd.to_numeric(parts[1], errors="coerce")
    return bool((first > 12).any() and not (second > 12).any())


def _try_datetime(name: str, series: pd.Series) -> tuple[pd.Series, int, bool] | None:
    present = series.dropna().astype(str)
    if present.empty:
        return None
    strict = present.map(lambda v: bool(STRICT_DATE_RE.match(v))).mean() >= PARSE_RATIO
    hinted = any(h in name for h in DATE_NAME_HINTS) and (
        present.map(lambda v: bool(YEAR_RE.search(v))).mean() >= PARSE_RATIO
    )
    if not (strict or hinted):
        return None

    day_first = _looks_day_first(present)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=day_first)
    if not pd.api.types.is_datetime64_any_dtype(parsed):
        return None
    valid = int(parsed.notna().sum())
    if valid / len(present) < PARSE_RATIO:
        return None
    return parsed, len(present) - valid, day_first


def _standardize_categories(series: pd.Series) -> tuple[pd.Series, dict[str, Any] | None]:
    """Merge spellings that differ only by case, e.g. 'hyd' and 'HYD' into 'Hyd'."""
    values = series.dropna()
    if values.empty:
        return series, None
    unique = values.nunique()
    if unique > MAX_CATEGORY_UNIQUE and unique / len(values) > 0.5:
        return series, None

    groups: dict[str, list[tuple[str, int]]] = {}
    for spelling, count in values.value_counts().items():
        groups.setdefault(str(spelling).casefold(), []).append((str(spelling), int(count)))

    mapping: dict[str, str] = {}
    merged: list[dict[str, Any]] = []
    for variants in groups.values():
        if len(variants) < 2:
            continue
        # prefer a properly cased spelling ("Hyd"), then the most frequent one
        variants.sort(key=lambda v: (v[0].islower() or v[0].isupper(), -v[1], v[0]))
        canonical = variants[0][0]
        others = [spelling for spelling, _ in variants[1:]]
        mapping.update({spelling: canonical for spelling in others})
        merged.append({"canonical": canonical, "variants": others})

    if not mapping:
        return series, None
    changed = int(series.isin(list(mapping)).sum())
    info = {"cells_changed": changed, "merged": merged[:5]}
    return series.map(lambda v: mapping.get(v, v)), info


# ---------- main entry point ----------

def clean_data(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = raw_df.copy()
    rows_before = len(df)

    # 1. Column names: safe, unique, lowercase
    new_names = _standardize_column_names(df.columns)
    columns_renamed = {
        str(old): new for old, new in zip(df.columns, new_names) if str(old) != new
    }
    df.columns = new_names

    # 2. Text: trim, collapse spaces, placeholders ("-", "N/A", "") become missing
    placeholders: dict[str, int] = {}
    for col in df.columns:
        if not _is_text(df[col]):
            continue
        before = int(df[col].isna().sum())
        df[col] = df[col].map(_normalize_text)
        converted = int(df[col].isna().sum()) - before
        if converted > 0:
            placeholders[col] = converted

    # 3. Empty rows and empty columns
    df = df.dropna(how="all")
    empty_rows_removed = rows_before - len(df)
    empty_columns = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty_columns)
    if df.empty or df.shape[1] == 0:
        raise DatasetError("The dataset has no usable data after cleaning.", 422)

    # 4. Type detection (numeric, dates) and spelling standardization
    conversions: dict[str, dict[str, Any]] = {}
    standardized: dict[str, dict[str, Any]] = {}
    for col in [c for c in df.columns if _is_text(df[c])]:
        numeric = _try_numeric(df[col])
        if numeric is not None:
            df[col], invalid = numeric
            conversions[col] = {"to": "numeric", "invalid_set_missing": invalid}
            continue
        dates = _try_datetime(col, df[col])
        if dates is not None:
            df[col], invalid, day_first = dates
            conversions[col] = {
                "to": "datetime",
                "invalid_set_missing": invalid,
                "day_first": day_first,
            }
            continue
        df[col], info = _standardize_categories(df[col])
        if info:
            standardized[col] = info

    # 5. Duplicates (after text cleaning, so "A " and "a" can match)
    duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates().reset_index(drop=True)

    # 6. Missing values
    missing_before = {c: int(n) for c, n in df.isna().sum().items() if n > 0}
    filled: dict[str, dict[str, Any]] = {}
    skipped_high: dict[str, float] = {}
    for col, count in missing_before.items():
        pct = count / len(df) * 100
        series = df[col]
        if pct > MAX_FILL_MISSING_PCT:
            skipped_high[col] = round(pct, 2)  # too empty: filling would invent data
            continue
        if pd.api.types.is_datetime64_any_dtype(series):
            continue  # never invent dates
        if pd.api.types.is_numeric_dtype(series):
            df[col] = series.fillna(series.median())
            method = "median"
        else:
            mode = series.mode()
            df[col] = series.fillna(mode.iloc[0] if not mode.empty else "unknown")
            method = "most frequent value"
        filled[col] = {"count": count, "method": method}

    # 7. Outliers (IQR). Flag only, never delete.
    outliers: dict[str, int] = {}
    outlier_details: dict[str, dict[str, Any]] = {}
    for col in df.select_dtypes(include="number").columns:
        values = df[col].dropna()
        if values.empty:
            continue
        q1, q3 = values.quantile(0.25), values.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
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
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
    }
    return df, report