from pydantic import BaseModel, Field

from app.security.passwords import MAX_PASSWORD_CHARS


class SessionOut(BaseModel):
    # A login is configured on this server: /api answers 401 without a session.
    auth_required: bool
    # This browser holds a valid session cookie (always false when no login is configured).
    authenticated: bool
    # Read-only public demo: writes answer 403 `demo_read_only`.
    demo_mode: bool


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARS)
