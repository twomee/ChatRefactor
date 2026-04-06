# app/services/exceptions.py — Domain exceptions for the service layer
#
# These exceptions decouple the service layer from HTTP concerns (FastAPI's
# HTTPException). Routers catch these and translate to appropriate HTTP status codes.


class ServiceError(Exception):
    """Base exception for service layer errors."""

    pass


class NotFoundError(ServiceError):
    """Raised when a requested resource does not exist."""

    def __init__(self, detail: str = "Not found"):
        self.detail = detail
        super().__init__(detail)


class ValidationError(ServiceError):
    """Raised when input validation fails at the service layer."""

    def __init__(self, detail: str = "Validation error"):
        self.detail = detail
        super().__init__(detail)
