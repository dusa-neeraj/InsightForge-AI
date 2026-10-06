import pandas as pd
import numpy as np


def clean_data(df: pd.DataFrame):
    report = {}
    report["rows_before"] = len(df)

    # 1. Standardize column names
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    # 2. Remove duplicates
    dupes = int(df.duplicated().sum())
    df = df.drop_duplicates()
    report["duplicates_removed"] = dupes

    # 3. Trim spaces in text columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace("nan", np.nan)

    # 4. Try converting text columns to numbers or dates
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() > 0.9:
            df[col] = converted
            continue
        if "date" in col or "time" in col:
            dates = pd.to_datetime(df[col], errors="coerce")
            if dates.notna().mean() > 0.9:
                df[col] = dates

    # 5. Missing values
    report["missing_before"] = {c: int(v) for c, v in df.isna().sum().items() if v > 0}
    for col in df.columns:
        if df[col].isna().any():
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(df[col].median())
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                continue
            else:
                mode = df[col].mode()
                df[col] = df[col].fillna(mode[0] if not mode.empty else "unknown")

    # 6. Detect outliers (IQR method), only flag, don't delete
    outliers = {}
    for col in df.select_dtypes(include=np.number).columns:
        q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        iqr = q3 - q1
        count = int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
        if count > 0:
            outliers[col] = count
    report["outliers_flagged"] = outliers

    report["rows_after"] = len(df)
    report["dtypes"] = {c: str(t) for c, t in df.dtypes.items()}
    return df, report