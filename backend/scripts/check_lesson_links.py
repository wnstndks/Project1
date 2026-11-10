"""Check that every lesson reference URL answers HTTP 200 (network; not part of pytest).

Run from `backend/`:

    $env:PYTHONPATH = "."; py -3.11 -m uv run python scripts/check_lesson_links.py
    $env:PYTHONPATH = "."; py -3.11 -m uv run python scripts/check_lesson_links.py --urls FILE

For each URL: HEAD first, then GET when HEAD is not 200 (many sites refuse HEAD). Prints one
line per reference with the status, the method that produced it and the final URL after
redirects, and exits 1 when any reference did not end at 200. Uses the backend's HTTP client
(`httpx2`) when importable and falls back to `urllib` otherwise. `--urls FILE` probes candidate
URLs listed one per line (blank lines and `#` comments ignored) instead of the catalog, for
checking references before they go into a lesson.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    import httpx2 as httpx
except ImportError:  # pragma: no cover - fallback outside the uv environment
    httpx = None  # type: ignore[assignment]

from app.learn.catalog import LESSONS

TIMEOUT = 10.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 asset-manager-lesson-link-check/1.0"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Language": "ko,en;q=0.8"}


@dataclass(frozen=True)
class Result:
    status: int | None
    final_url: str
    method: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200


def _probe_httpx(url: str) -> Result:
    assert httpx is not None
    last: Result | None = None
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        for method in ("HEAD", "GET"):
            try:
                resp = client.request(method, url)
            except httpx.HTTPError as exc:
                last = Result(None, url, method, f"{type(exc).__name__}: {exc}")
                continue
            last = Result(resp.status_code, str(resp.url), method)
            if last.ok:
                return last
    assert last is not None
    return last


def _probe_urllib(url: str) -> Result:
    last: Result | None = None
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, headers=HEADERS, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
                last = Result(resp.status, resp.geturl(), method)
        except urllib.error.HTTPError as exc:
            last = Result(exc.code, exc.geturl() or url, method)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = Result(None, url, method, f"{type(exc).__name__}: {exc}")
        if last.ok:
            return last
    assert last is not None
    return last


def probe(url: str) -> Result:
    return _probe_httpx(url) if httpx is not None else _probe_urllib(url)


def _format(result: Result, url: str, label: str) -> str:
    mark = "ok " if result.ok else "FAIL"
    status = result.status if result.status is not None else "ERR"
    line = f"  {mark} {label} {status:<4} {result.method:<4} {url}"
    if result.final_url != url:
        line += f"\n        -> {result.final_url}"
    if result.detail:
        line += f"\n        {result.detail}"
    return line


def check_candidates(path: Path) -> int:
    urls = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    failures = 0
    for url in urls:
        result = probe(url)
        print(_format(result, url, "-"))
        failures += 0 if result.ok else 1
    print(f"\n{len(urls) - failures}/{len(urls)} candidate URLs answered 200")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--urls", type=Path, help="probe the URLs in this file instead")
    args = parser.parse_args(argv)
    if args.urls is not None:
        return check_candidates(args.urls)

    failures = 0
    seen: dict[str, Result] = {}
    for lesson in LESSONS.values():
        print(f"[{lesson.id}]")
        for i, ref in enumerate(lesson.references, start=1):
            result = seen.get(ref.url)
            if result is None:
                result = probe(ref.url)
                seen[ref.url] = result
            print(_format(result, ref.url, f"[{i}]"))
            if not result.ok:
                failures += 1
    total = sum(len(x.references) for x in LESSONS.values())
    print(f"\n{total - failures}/{total} references answered 200 ({len(seen)} unique URLs)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
