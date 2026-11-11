"""Startup rules for a deployed instance (DECISIONS.md D-035), as pure functions.

`Settings` calls `deployment_problem` from a model validator, so a server that would be open
to the internet without a login or the demo lock refuses to start. Messages name the setting
but never include a secret value.
"""

from app.security.passwords import PasswordHashError, parse_hash

MIN_SESSION_SECRET_BYTES = 32

# Default policy for the built single-page app served from the same origin. `style-src` keeps
# 'unsafe-inline' because the chart libraries write style attributes; scripts are same-origin
# files only, so index.html must not carry an inline script. Override with
# AM_CONTENT_SECURITY_POLICY when the built frontend needs something else.
DEFAULT_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def deployment_problem(
    *,
    production: bool,
    demo_mode: bool,
    real_orders_enabled: bool,
    password_hash: str | None,
    session_secret: str | None,
) -> str | None:
    """Why this combination of settings must not start, or None when it may."""
    if demo_mode and real_orders_enabled:
        return "AM_DEMO_MODE cannot be combined with real orders: a public demo never trades"

    if (
        session_secret is not None
        and len(session_secret.encode("utf-8")) < MIN_SESSION_SECRET_BYTES
    ):
        return f"AM_SESSION_SECRET must be at least {MIN_SESSION_SECRET_BYTES} bytes"

    if password_hash is not None:
        try:
            parsed = parse_hash(password_hash)
        except PasswordHashError as exc:
            return f"AM_AUTH_PASSWORD_HASH: {exc}"
        if session_secret is None:
            return "AM_AUTH_PASSWORD_HASH needs AM_SESSION_SECRET to sign session cookies"
        if production and not parsed.strong_enough_for_production:
            return (
                "AM_AUTH_PASSWORD_HASH is too cheap for production; create it with "
                "`python -m app.security.hash_password`"
            )

    if production and not demo_mode and password_hash is None:
        return (
            "AM_ENV=production needs either AM_DEMO_MODE (read-only demo) or a login "
            "(AM_AUTH_PASSWORD_HASH and AM_SESSION_SECRET)"
        )
    return None
