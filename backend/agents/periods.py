import calendar
import re

import pandas as pd

from agents.trends import _grain, _is_partial_last, _period_labels
from utils.errors import PlanError

MONTHS: dict[str, int] = {}
for _i in range(1, 13):
    MONTHS[calendar.month_name[_i].lower()] = _i
    MONTHS[calendar.month_abbr[_i].lower()] = _i
MONTHS["sept"] = 9

LATEST_WORDS = {"latest", "last", "recent", "this", "current"}


def resolve_period(
    df: pd.DataFrame, column: str, period: str | None, grain: str | None
) -> tuple[str, str]:
    """Turn 'July', '2024-07', 'July 2023', a date or 'latest' into (label, grain)."""
    dates = df[column].dropna()
    if dates.empty:
        raise PlanError(f"'{column}' has no dates.")
    text = (period or "latest").strip().lower()

    if text in LATEST_WORDS or text.startswith(("last ", "this ", "latest")):
        grain = grain or _grain(int((dates.max() - dates.min()).days))
        labels = sorted(set(_period_labels(dates, grain)))
        if len(labels) > 2 and _is_partial_last(dates.max(), grain):
            labels = labels[:-1]  # skip a period that is still in progress
        return labels[-1], grain

    match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if match:
        return f"{int(match[1]):04d}-{int(match[2]):02d}", "month"

    match = re.fullmatch(r"([a-z]+)\.?\s*(\d{4})?", text)
    if match and match[1] in MONTHS:
        month = MONTHS[match[1]]
        if match[2]:
            year = int(match[2])
        else:  # no year given: use the latest year that has this month
            years = sorted(set(dates[dates.dt.month == month].dt.year))
            if not years:
                raise PlanError(f"There is no data for {calendar.month_name[month]}.")
            year = int(years[-1])
        return f"{year:04d}-{month:02d}", "month"

    try:
        stamp = pd.Timestamp(text)
    except (ValueError, TypeError):
        raise PlanError(
            f"I couldn't understand the period '{period}'. Try a month like 'July' or '2024-07'."
        ) from None
    if pd.isna(stamp):
        raise PlanError(f"I couldn't understand the period '{period}'.")
    grain = grain or "day"
    return str(_period_labels(pd.Series([stamp]), grain).iloc[0]), grain


def previous_period(label: str, grain: str) -> str:
    """The calendar period right before this one, in the same label format."""
    if grain == "month":
        return str(pd.Period(label, freq="M") - 1)
    step = pd.Timedelta(days=7 if grain == "week" else 1)
    return (pd.Timestamp(label) - step).strftime("%Y-%m-%d")