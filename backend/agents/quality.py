from typing import Any

SCORE_WEIGHTS = {"completeness": 0.5, "uniqueness": 0.25, "outliers": 0.25}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

# Columns with these words in the name should not contain negative values
NON_NEGATIVE_WORDS = {
    "price", "amount", "quantity", "qty", "salary", "revenue",
    "sales", "cost", "age", "count", "total", "units",
}


def _grade(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


def _outlier_cells(profile: dict[str, Any]) -> tuple[int, int]:
    """Returns (outlier cells, total non-missing numeric cells)."""
    rows = profile["overview"]["rows"]
    outliers = cells = 0
    for col in profile["columns"]:
        if col["kind"] == "numeric":
            outliers += col.get("outlier_count", 0)
            cells += rows - col["missing"]
    return outliers, cells


def quality_score(profile: dict[str, Any]) -> dict[str, Any]:
    overview = profile["overview"]
    outlier_cells, numeric_cells = _outlier_cells(profile)
    outlier_rate = outlier_cells / numeric_cells * 100 if numeric_cells else 0.0

    components = {
        "completeness": max(0.0, 100 - overview["missing_pct"]),
        "uniqueness": max(0.0, 100 - overview["duplicate_pct"]),
        "outliers": max(0.0, 100 - outlier_rate * 5),
    }
    score = sum(components[name] * weight for name, weight in SCORE_WEIGHTS.items())
    return {
        "score": round(score, 1),
        "grade": _grade(score),
        "components": {name: round(v, 1) for name, v in components.items()},
    }


def _snapshot(profile: dict[str, Any]) -> dict[str, Any]:
    overview = profile["overview"]
    outlier_cells, _ = _outlier_cells(profile)
    return {
        "rows": overview["rows"],
        "columns": overview["columns"],
        "duplicate_rows": overview["duplicate_rows"],
        "missing_cells": overview["missing_cells"],
        "missing_pct": overview["missing_pct"],
        "outlier_cells": outlier_cells,
        **quality_score(profile),
    }


def build_changes(
    cleaning_report: dict[str, Any],
    raw_profile: dict[str, Any],
    clean_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Turn the cleaning report into readable change entries."""
    changes: list[dict[str, Any]] = []

    def add(kind: str, message: str, **extra: Any) -> None:
        changes.append({"type": kind, "message": message, **extra})

    renamed = cleaning_report.get("columns_renamed", {})
    if renamed:
        add("columns_renamed", f"Standardized {len(renamed)} column name(s)", count=len(renamed))

    rows_removed = cleaning_report.get("empty_rows_removed", 0)
    if rows_removed:
        add("empty_rows_removed", f"Removed {rows_removed} completely empty row(s)", count=rows_removed)

    for name in cleaning_report.get("empty_columns_dropped", []):
        add("empty_column_dropped", f"Dropped empty column '{name}'", column=name)

    for name, count in cleaning_report.get("placeholders_to_missing", {}).items():
        add("placeholders_to_missing",
            f"Converted {count} placeholder value(s) (like '-' or 'N/A') in '{name}' to missing",
            column=name, count=count)

    for name, info in cleaning_report.get("type_conversions", {}).items():
        message = f"Converted '{name}' to {info['to']}"
        if info.get("invalid_set_missing"):
            message += f" ({info['invalid_set_missing']} invalid value(s) set to missing)"
        if info.get("day_first"):
            message += ", read dates as day-first (DD/MM/YYYY)"
        add("type_converted", message, column=name)

    for name, info in cleaning_report.get("values_standardized", {}).items():
        example = info["merged"][0]
        add("values_standardized",
            f"Standardized {info['cells_changed']} inconsistent value(s) in '{name}' "
            f"(e.g. '{example['variants'][0]}' became '{example['canonical']}')",
            column=name, count=info["cells_changed"])

    dupes = cleaning_report.get(
        "duplicates_removed", raw_profile["overview"]["duplicate_rows"]
    )
    if dupes:
        add("duplicates_removed", f"Removed {dupes} duplicate row(s)", count=dupes)

    clean_cols = {c["name"]: c for c in clean_profile["columns"]}
    fill_info = cleaning_report.get("missing_filled", {})
    skipped = cleaning_report.get("missing_skipped_high", {})
    for name, before in cleaning_report.get("missing_before", {}).items():
        col = clean_cols.get(name)
        remaining = col["missing"] if col else 0
        filled = before - remaining
        if filled > 0:
            method = fill_info.get(name, {}).get("method") or (
                "median" if col and col["kind"] == "numeric" else "most frequent value"
            )
            add("missing_filled",
                f"Filled {filled} missing value(s) in '{name}' with the {method}",
                column=name, count=filled)
        if remaining > 0:
            reason = " (too many missing to fill safely)" if name in skipped else ""
            add("missing_left", f"Left {remaining} missing value(s) in '{name}' unfilled{reason}",
                column=name, count=remaining)

    for name, count in cleaning_report.get("outliers_flagged", {}).items():
        add("outliers_flagged", f"Flagged {count} outlier(s) in '{name}' (kept in the data)",
            column=name, count=count)

    if not changes:
        add("no_changes", "No cleaning changes were needed")
    return changes

def _issue(severity: str, column: str | None, kind: str, message: str) -> dict[str, Any]:
    return {"severity": severity, "column": column, "type": kind, "message": message}


def find_issues(clean_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Problems or warnings that remain in the cleaned data."""
    issues: list[dict[str, Any]] = []
    rows = clean_profile["overview"]["rows"]

    if rows < 30:
        issues.append(
            _issue("info", None, "small_dataset",
                   f"Only {rows} rows. Statistics may not be reliable.")
        )

    for col in clean_profile["columns"]:
        name = col["name"]

        if rows and col["missing"] == rows:
            issues.append(_issue("high", name, "empty_column", f"'{name}' is completely empty"))
            continue

        if col["missing"]:
            pct = col["missing_pct"]
            severity = "high" if pct >= 40 else "medium" if pct >= 10 else "low"
            issues.append(
                _issue(severity, name, "missing_values",
                       f"'{name}' still has {col['missing']} missing value(s) ({pct}%)")
            )

        if col.get("outlier_count"):
            pct = col["outlier_pct"]
            issues.append(
                _issue("medium" if pct >= 5 else "low", name, "outliers",
                       f"'{name}' has {col['outlier_count']} outlier(s) ({pct}%), kept in the data")
            )

        if col["kind"] != "date" and col["unique"] == 1:
            issues.append(
                _issue("low", name, "constant_column", f"'{name}' has only one distinct value")
            )

        if col["likely_id"]:
            issues.append(
                _issue("info", name, "likely_id",
                       f"'{name}' looks like an identifier, not useful for analysis")
            )
        elif col["kind"] == "categorical" and col["unique"] > 50 and col["cardinality_pct"] >= 50:
            issues.append(
                _issue("info", name, "high_cardinality",
                       f"'{name}' has {col['unique']} distinct values, hard to chart")
            )

        if (
            col["kind"] == "numeric"
            and col.get("min") is not None
            and col["min"] < 0
            and NON_NEGATIVE_WORDS & set(name.split("_"))
        ):
            issues.append(
                _issue("medium", name, "negative_values",
                       f"'{name}' has negative values (minimum {col['min']})")
            )

    issues.sort(key=lambda i: SEVERITY_ORDER[i["severity"]])
    return issues


def build_quality_report(
    raw_profile: dict[str, Any],
    clean_profile: dict[str, Any],
    cleaning_report: dict[str, Any],
) -> dict[str, Any]:
    before = _snapshot(raw_profile)
    after = _snapshot(clean_profile)
    issues = find_issues(clean_profile)

    return {
        "before": before,
        "after": after,
        "score_improvement": round(after["score"] - before["score"], 1),
        "score_weights": SCORE_WEIGHTS,
        "changes": build_changes(cleaning_report, raw_profile, clean_profile),
        "issues": issues,
        "issue_counts": {
            level: sum(1 for i in issues if i["severity"] == level)
            for level in SEVERITY_ORDER
        },
    }