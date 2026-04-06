# app/services/exceptions.py — Domain exceptions for service layer
"""
These exceptions decouple service logic from HTTP transport concerns.
Routers catch them and convert to appropriate HTTP responses.
"""


class ServiceError(Exception):
    """Base exception for service layer errors."""

    pass


class NotFoundError(ServiceError):
    """Resource not found."""

    def __init__(self, detail: str = "Not found"):
        self.detail = detail
        super().__init__(detail)


class AuthenticationError(ServiceError):
    """Authentication failed."""

    def __init__(self, detail: str = "Authentication failed"):
        self.detail = detail
        super().__init__(detail)


class ConflictError(ServiceError):
    """Resource state conflict."""

    def __init__(self, detail: str = "Conflict"):
        self.detail = detail
        super().__init__(detail)


class BadRequestError(ServiceError):
    """Bad request / validation error."""

    def __init__(self, detail: str = "Bad request"):
        self.detail = detail
        super().__init__(detail)


class ServerError(ServiceError):
    """Internal server error."""

    def __init__(self, detail: str = "Internal error"):
        self.detail = detail
        super().__init__(detail)
