"""Service-layer exceptions."""


class ServiceError(RuntimeError):
    """Business error that can be mapped to an HTTP response by routes."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(ServiceError):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class ConflictError(ServiceError):
    """Raised when a request conflicts with current state."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)
