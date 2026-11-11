"""Password hashing for the single-account login (DECISIONS.md D-035).

scrypt from the standard library, encoded as `scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>` so
the cost parameters travel with the hash. Errors raised here never contain the password or
the hash, so a startup failure cannot print either one.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass, field

SCHEME = "scrypt"
# OWASP's scrypt setting with about 32 MiB per verification (N=2^15, r=8, p=3): small enough
# for a one-worker container, a few hundred milliseconds per login.
DEFAULT_N = 2**15
DEFAULT_R = 8
DEFAULT_P = 3
SALT_BYTES = 16
KEY_BYTES = 32
MAX_PASSWORD_CHARS = 1024

# What a configured hash may ask for. The upper bounds keep a typo in the cost fields from
# allocating gigabytes on every login; the production floor refuses hand-made weak hashes.
MAX_N = 2**17
MAX_R = 16
MAX_P = 16
MIN_PRODUCTION_N = 2**14
MIN_PRODUCTION_R = 8

FORMAT_HINT = (
    "expected scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64> as printed by "
    "`python -m app.security.hash_password`; keep it in single quotes so a shell or "
    "compose file does not expand the $ signs"
)


class PasswordHashError(ValueError):
    """The configured hash is malformed. The message never contains the hash itself."""


@dataclass(frozen=True)
class ScryptHash:
    n: int
    r: int
    p: int
    salt: bytes = field(repr=False)
    key: bytes = field(repr=False)

    @property
    def strong_enough_for_production(self) -> bool:
        return self.n >= MIN_PRODUCTION_N and self.r >= MIN_PRODUCTION_R


def _b64encode(raw: bytes) -> str:
    # URL-safe and unpadded: no "+", "/" or "=" for an env file to trip over.
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    """Either base64 alphabet, with or without padding."""
    normalized = text.replace("+", "-").replace("/", "_").rstrip("=")
    padded = normalized + "=" * (-len(normalized) % 4)
    try:
        return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise PasswordHashError(f"invalid base64 in the password hash ({FORMAT_HINT})") from None


def parse_hash(encoded: str) -> ScryptHash:
    parts = encoded.strip().split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        raise PasswordHashError(f"not a scrypt password hash ({FORMAT_HINT})")
    try:
        n, r, p = (int(x) for x in parts[1:4])
    except ValueError:
        raise PasswordHashError(f"non-numeric scrypt cost ({FORMAT_HINT})") from None
    if not (2 <= n <= MAX_N and n & (n - 1) == 0):
        raise PasswordHashError(f"scrypt n must be a power of two between 2 and {MAX_N}")
    if not (1 <= r <= MAX_R and 1 <= p <= MAX_P):
        raise PasswordHashError(f"scrypt r and p must be within 1..{MAX_R} and 1..{MAX_P}")
    salt, key = _b64decode(parts[4]), _b64decode(parts[5])
    if len(salt) < 8 or not (16 <= len(key) <= 64):
        raise PasswordHashError(f"salt or hash has the wrong length ({FORMAT_HINT})")
    return ScryptHash(n=n, r=r, p=p, salt=salt, key=key)


def _derive(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    # NFKC so the same passphrase typed on another keyboard or OS hashes identically.
    raw = unicodedata.normalize("NFKC", password).encode("utf-8")
    # OpenSSL refuses anything above 32 MiB unless told otherwise; ask for what n, r and p
    # need plus a little room.
    maxmem = 128 * r * (n + p + 2) + 1024 * 1024
    return hashlib.scrypt(raw, salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=length)


def hash_password(
    password: str, *, n: int = DEFAULT_N, r: int = DEFAULT_R, p: int = DEFAULT_P
) -> str:
    if not password or len(password) > MAX_PASSWORD_CHARS:
        raise ValueError(f"password must be 1..{MAX_PASSWORD_CHARS} characters")
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(password, salt, n, r, p, KEY_BYTES)
    encoded = f"{SCHEME}${n}${r}${p}${_b64encode(salt)}${_b64encode(key)}"
    parse_hash(encoded)  # never print a hash the server would then refuse
    return encoded


def verify_password(password: str, expected: ScryptHash) -> bool:
    """Constant-time comparison of the derived key. Oversized or empty input is refused
    without hashing (it cannot be the password: the CLI enforces the same bounds)."""
    if not password or len(password) > MAX_PASSWORD_CHARS:
        return False
    derived = _derive(
        password, expected.salt, expected.n, expected.r, expected.p, len(expected.key)
    )
    return hmac.compare_digest(derived, expected.key)
