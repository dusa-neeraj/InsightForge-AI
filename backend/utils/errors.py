class DatasetError(Exception):
    """Error with a safe, user-friendly message."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class PlanError(Exception):
    """A question or plan cannot be run safely. The message is written for end users."""


class SqlError(Exception):
    """A SQL query failed to run. The message is safe to show to users."""


class SqlRejected(SqlError):
    """A SQL query broke the safety rules and was not run."""