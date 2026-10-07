import re
import sqlite3
import time
from typing import Any

import pandas as pd

from agents.profiling import _num as to_number, column_kind
from utils.errors import SqlError, SqlRejected

TABLE = "data"
MAX_ROWS = 1000
MAX_SQL_LENGTH = 2000
TIMEOUT_SECONDS = 3.0

ALLOWED_FUNCTIONS = {
    # aggregates
    "count", "sum", "avg", "min", "max", "total", "group_concat",
    # math and text
    "round", "abs", "floor", "ceil", "sqrt", "power",
    "coalesce", "ifnull", "nullif", "iif",
    "lower", "upper", "length", "substr", "substring", "trim", "ltrim", "rtrim",
    "replace", "instr",
    # inside SQLite, LIKE and GLOB are function calls
    "like", "glob",
    # dates are stored as text: YYYY-MM-DD
    "date", "time", "datetime", "julianday", "strftime",
    # window functions
    "row_number", "rank", "dense_rank", "lag", "lead",
}
BANNED_WORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "pragma", "vacuum", "reindex", "analyze", "begin", "commit", "rollback",
    "savepoint", "release",
}
LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")  # 'text' and "identifier"
WORD_RE = re.compile(r"[a-z_][a-z0-9_]*")


# ---------- layer 2: text checks ----------

def check_sql(sql: str | None) -> str:
    """Reject anything that is not a single, comment-free SELECT. Returns the cleaned query."""
    text = (sql or "").strip()
    if not text:
        raise SqlRejected("Write a SELECT query first.")
    if len(text) > MAX_SQL_LENGTH:
        raise SqlRejected(f"The query is too long (maximum {MAX_SQL_LENGTH:,} characters).")

    masked = LITERAL_RE.sub("''", text)  # hide quoted text so it can't trigger the checks
    leftover = masked.replace("''", "")
    if "'" in leftover or '"' in leftover:
        raise SqlRejected("The query has an unclosed quote.")
    if "--" in masked or "/*" in masked or "*/" in masked:
        raise SqlRejected("Comments are not allowed in queries.")

    body = masked.rstrip().rstrip(";").rstrip()  # one trailing semicolon is fine
    if ";" in body:
        raise SqlRejected("Only one statement is allowed.")

    words = WORD_RE.findall(body.lower())
    if not words or words[0] not in ("select", "with"):
        raise SqlRejected("Only SELECT queries are allowed.")
    for word in words:
        if word in BANNED_WORDS:
            raise SqlRejected(f"'{word.upper()}' is not allowed. Only read-only SELECT queries can run.")
        if word.startswith(("sqlite_", "pragma_")):
            raise SqlRejected("System tables and pragma functions are not available.")
    return text.rstrip().rstrip(";").rstrip()


# ---------- the throwaway database ----------

def _quote(name: Any) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sqlite_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    if column_kind(series) == "numeric":
        return "INTEGER" if pd.api.types.is_integer_dtype(series) else "REAL"
    return "TEXT"


def _load(df: pd.DataFrame) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    frame = df.copy()
    for col in frame.columns:
        series = frame[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            present = series.dropna()
            has_time = bool((present != present.dt.normalize()).any())
            frame[col] = series.dt.strftime("%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d")
        elif pd.api.types.is_bool_dtype(series):
            frame[col] = series.astype(int)

    columns = ", ".join(f"{_quote(c)} {sqlite_type(df[c])}" for c in frame.columns)
    conn.execute(f"CREATE TABLE {TABLE} ({columns})")
    rows = frame.astype(object).where(frame.notna(), None).itertuples(index=False, name=None)
    placeholders = ", ".join("?" * len(frame.columns))
    conn.executemany(f"INSERT INTO {TABLE} VALUES ({placeholders})", rows)
    conn.commit()
    return conn


# ---------- layer 3: the authorizer ----------

def _authorizer(denied: list[str]):
    recursive = getattr(sqlite3, "SQLITE_RECURSIVE", 33)

    def check(action, arg1, arg2, db_name, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if arg1 == TABLE:
                return sqlite3.SQLITE_OK
            denied.append(f"the table '{arg1}'")
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            name = (arg2 or "").lower()
            if name in ALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_OK
            denied.append(f"the function '{name}'")
            return sqlite3.SQLITE_DENY
        if action == recursive:
            denied.append("a recursive query")
        else:
            denied.append("a statement that is not a plain SELECT")
        return sqlite3.SQLITE_DENY

    return check


def _translate(exc: sqlite3.Error, denied: list[str]) -> SqlError:
    if denied:
        return SqlRejected(
            f"That query isn't allowed: it uses {denied[0]}. Only read-only SELECT queries "
            f"on the '{TABLE}' table with standard functions can be run."
        )
    message = str(exc)
    if "interrupted" in message.lower():
        return SqlError(f"The query took longer than {TIMEOUT_SECONDS:g} seconds and was stopped.")
    return SqlError(f"SQL error: {message}")


def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return to_number(value)
    if isinstance(value, bytes):
        return "<binary data>"
    return str(value)


# ---------- the only way queries are run ----------

def run_select(df: pd.DataFrame, sql: str) -> dict[str, Any]:
    query = check_sql(sql)
    conn = _load(df)
    denied: list[str] = []
    try:
        conn.execute("PRAGMA query_only = ON")  # layer 4: no writes, whatever happens
        conn.set_authorizer(_authorizer(denied))
        deadline = time.monotonic() + TIMEOUT_SECONDS  # layer 5: timeout
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        started = time.monotonic()
        try:
            cursor = conn.execute(query)
            fetched = cursor.fetchmany(MAX_ROWS + 1)  # layer 6: row cap
            columns = [d[0] for d in cursor.description or []]
        except sqlite3.Error as exc:
            raise _translate(exc, denied) from None
        elapsed = int((time.monotonic() - started) * 1000)
    finally:
        conn.close()

    truncated = len(fetched) > MAX_ROWS
    rows = [[_cell(v) for v in row] for row in fetched[:MAX_ROWS]]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": elapsed,
    }