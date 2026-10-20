class DomainError(Exception):
    """A request that is well-formed but violates a business rule. Mapped to HTTP 422.

    `code` is an optional machine-readable reason the frontend can branch on, so it never
    has to parse the (Korean or English) message.
    """

    status_code = 422

    def __init__(self, message: str = "", code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class UpstreamError(DomainError):
    """An external service (e.g. the Claude API) failed or is unavailable."""

    status_code = 502
