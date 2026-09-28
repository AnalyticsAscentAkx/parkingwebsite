"""Conditional-GET downloader for the DOT-NL bulk files.

The feeds honour ETag and Last-Modified, so a re-run inside a refresh window
costs one 304 instead of tens of megabytes. Never blind-download.
"""
import gzip
import time
from dataclasses import dataclass

import httpx
import orjson

from . import config, db


@dataclass
class Fetched:
    url: str
    changed: bool           # False when the server answered 304
    body: bytes | None
    etag: str | None
    last_modified: str | None
    elapsed_s: float


def _prior(url: str) -> dict:
    # The cache is a courtesy to the upstream feed, not a dependency. Feed-only
    # runs (page preview, a fresh checkout) work with no database at all.
    try:
        row = db.one(
            "SELECT etag, last_modified FROM fetch_state WHERE url = %s", (url,)
        )
    except Exception:
        return {}
    return row or {}


def _remember(url: str, resp: httpx.Response, size: int) -> None:
    try:
        _remember_db(url, resp, size)
    except Exception:
        pass  # no database: nothing to remember, next run just re-downloads


def _remember_db(url: str, resp: httpx.Response, size: int) -> None:
    db.execute(
        """INSERT INTO fetch_state (url, etag, last_modified, fetched_at, bytes)
           VALUES (%s, %s, %s, now(), %s)
           ON CONFLICT (url) DO UPDATE SET
             etag = EXCLUDED.etag,
             last_modified = EXCLUDED.last_modified,
             fetched_at = EXCLUDED.fetched_at,
             bytes = EXCLUDED.bytes""",
        (url, resp.headers.get("etag"), resp.headers.get("last-modified"), size),
    )


def get(url: str, force: bool = False, timeout: float = 180.0) -> Fetched:
    headers = {"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip"}
    if not force:
        prior = _prior(url)
        if prior.get("etag"):
            headers["If-None-Match"] = prior["etag"]
        if prior.get("last_modified"):
            headers["If-Modified-Since"] = prior["last_modified"]

    t0 = time.monotonic()
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
    elapsed = time.monotonic() - t0

    if resp.status_code == 304:
        return Fetched(url, False, None, headers.get("If-None-Match"),
                       headers.get("If-Modified-Since"), elapsed)
    resp.raise_for_status()

    body = resp.content
    # httpx transparently un-gzips a gzip *Content-Encoding*. These URLs are
    # gzip *files*, so the magic number may still be there afterwards.
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)

    _remember(url, resp, len(body))
    return Fetched(url, True, body, resp.headers.get("etag"),
                   resp.headers.get("last-modified"), elapsed)


def get_json(url: str, force: bool = False):
    f = get(url, force=force)
    if not f.changed or f.body is None:
        return None
    return orjson.loads(f.body)
