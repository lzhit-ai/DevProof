class DomainError(Exception):
    """Expected business error mapped to a stable HTTP error response."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
