class DomainError(Exception):
    """A request that is well-formed but violates a business rule. Mapped to HTTP 422."""

    status_code = 422


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409
