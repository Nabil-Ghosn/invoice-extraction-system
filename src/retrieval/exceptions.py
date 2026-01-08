class QueryError(Exception):
    """Base exception for query-related errors."""

    pass


class InvalidDateFormatError(QueryError):
    """Raised when date parsing fails."""

    def __init__(self, date_str: str, field_name: str) -> None:
        self.date_str: str = date_str
        self.field_name: str = field_name
        super().__init__(
            f"Invalid date format for {field_name}: '{date_str}'. "
            f"Expected format: YYYY-MM-DD"
        )


class DatabaseQueryError(QueryError):
    """Raised when database query execution fails."""

    pass
