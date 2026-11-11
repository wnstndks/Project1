"""Create the value for AM_AUTH_PASSWORD_HASH.

    py -m uv run python -m app.security.hash_password

Asks for the password twice without echoing it and prints one line: the scrypt hash. The
password is never written anywhere; put the printed line in backend/.env yourself (in single
quotes, so nothing expands the $ signs). Reads no settings and no .env file.
"""

import getpass
import sys
from collections.abc import Callable

from app.security.passwords import MAX_PASSWORD_CHARS, hash_password

MIN_PASSWORD_CHARS = 12


def main(prompt: Callable[[str], str] = getpass.getpass) -> int:
    first = prompt("New password: ")
    if not (MIN_PASSWORD_CHARS <= len(first) <= MAX_PASSWORD_CHARS):
        print(
            f"The password must be {MIN_PASSWORD_CHARS} to {MAX_PASSWORD_CHARS} characters.",
            file=sys.stderr,
        )
        return 1
    if prompt("Again: ") != first:
        print("The two entries differ. Nothing was created.", file=sys.stderr)
        return 1
    print(hash_password(first))
    print(
        "Put the line above in backend/.env as AM_AUTH_PASSWORD_HASH='...' (single quotes), "
        "next to an AM_SESSION_SECRET of 32 bytes or more.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
