"""Serve the built frontend from the API process (DECISIONS.md D-035).

One container serves both: `AM_STATIC_DIR` holds the output of `vite build` (index.html, the
hashed files under assets/, and what frontend/public/ adds). Nothing is mounted and no route
is added. `install` wraps the router's fallback, the handler Starlette calls only after no
route matched, so:

- every API route, its 404 and 405 answers and the middleware stack stay exactly as they are;
- a path under /api that matches nothing still gets the JSON 404, never the HTML page;
- app-wide dependencies (the demo's ticker guard) do not run for a file or a page.

For any other GET or HEAD: a file that exists under the folder is sent as it is; a missing
path with a build-file suffix (.js, .css, ...) is a 404; everything else is a page of the
single-page app and gets index.html, which then routes on the client.

This cannot be a `StaticFiles` mount on /assets: the page /assets/:symbol shares that prefix
with Vite's output folder, so /assets/AAA is a page while /assets/index-<hash>.js is a file.
"""

import logging
import re
from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.security.paths import is_api, route_path

log = logging.getLogger(__name__)

INDEX = "index.html"
# Vite names its bundled output <name>-<8-character content hash>.<ext> under assets/: the
# same name is always the same bytes, so it may be cached for good. Everything else
# (index.html, files copied from public/) keeps its name across builds and is revalidated on
# every load.
HASHED_DIR = "assets"
HASHED_NAME = re.compile(r"-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")
CACHE_HASHED = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "no-cache"

# What a build can contain, by suffix. Stated here rather than guessed: Python's table follows
# the operating system (on Windows the registry may say .js is text/plain, which a browser
# refuses to run under nosniff). A missing path with one of these suffixes is a missing file
# (404), not a page. Ticker suffixes on page paths (/assets/BRK.B) are not in this list.
MEDIA_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".map": "application/json",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".wasm": "application/wasm",
}


class Frontend:
    """The router's fallback when a built frontend is configured (see the module docstring)."""

    def __init__(self, directory: Path, not_found: ASGIApp) -> None:
        self.root = directory.resolve()
        self.index = self.root / INDEX
        self.not_found = not_found

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("GET", "HEAD"):
            await self.not_found(scope, receive, send)
            return
        path = route_path(scope)
        if is_api(path):
            await self.not_found(scope, receive, send)
            return

        file = await run_in_threadpool(self.file_for, path)
        if file is None and PurePosixPath(path).suffix.lower() in MEDIA_TYPES:
            await self.not_found(scope, receive, send)
            return
        response = self.page() if file is None else self.file(file)
        await response(scope, receive, send)

    def file_for(self, path: str) -> Path | None:
        """The file under the folder that this URL path names, or None.

        Dot-files are never served, which also drops every `.` and `..` segment. Whatever is
        left must still resolve to a regular file inside the folder: an absolute path, a
        drive letter, a backslash trick or a symlink pointing out all end up outside it.
        """
        parts = [part for part in path.split("/") if part]
        if not parts or any(part.startswith(".") for part in parts):
            return None
        try:
            candidate = self.root.joinpath(*parts).resolve()
            inside = candidate.is_relative_to(self.root) and candidate.is_file()
        except (OSError, ValueError):  # a NUL byte, a name the file system refuses
            return None
        return candidate if inside else None

    def file(self, file: Path) -> FileResponse:
        hashed = (
            file.relative_to(self.root).parts[0] == HASHED_DIR
            and HASHED_NAME.search(file.name) is not None
        )
        return FileResponse(
            file,
            media_type=MEDIA_TYPES.get(file.suffix.lower()),
            headers={"Cache-Control": CACHE_HASHED if hashed else CACHE_REVALIDATE},
        )

    def page(self) -> FileResponse:
        # Never cached without asking: it names the hashed files of the current build.
        return FileResponse(
            self.index,
            media_type=MEDIA_TYPES[".html"],
            headers={"Cache-Control": CACHE_REVALIDATE},
        )


def install(app: FastAPI, directory: Path) -> None:
    """Serve the frontend built into `directory` for everything the routes do not answer.

    A folder without index.html stops the server here: a public instance that silently
    serves the API alone would look like a blank site.
    """
    if not (directory / INDEX).is_file():
        raise RuntimeError(
            f"AM_STATIC_DIR={directory} has no {INDEX}. Build the frontend "
            "(`npm run build` in frontend/) or leave AM_STATIC_DIR unset."
        )
    app.router.default = Frontend(directory, app.router.default)
    log.info("serving the built frontend from %s", directory.resolve())
