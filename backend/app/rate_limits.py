"""SQLite-backed request throttling shared by all backend workers."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from contextlib import closing

from fastapi import HTTPException, status

from app.database import connect_db

AUTH_WINDOW_SECONDS = 300
AUTH_IP_LIMIT = 20
AUTH_IDENTITY_LIMIT = 10


def client_ip(client_host: str | None) -> str:
    """Use the ASGI peer address; forwarded headers are ignored without a trusted proxy."""
    return client_host or "unknown"


def enforce_rate_limit(
    bucket_keys: Sequence[str],
    *,
    limits: Sequence[int] | None = None,
    window_seconds: int = AUTH_WINDOW_SECONDS,
    now: int | None = None,
) -> None:
    """Atomically consume persistent buckets and raise 429 once any bucket is exhausted."""
    if not bucket_keys:
        return
    bucket_limits = list(limits or [AUTH_IP_LIMIT] * len(bucket_keys))
    if len(bucket_limits) != len(bucket_keys) or any(limit < 1 for limit in bucket_limits):
        raise ValueError("Rate limit keys and positive limits must have matching lengths")
    timestamp = int(time.time()) if now is None else now
    retry_after = 0
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        for key, limit in zip(bucket_keys, bucket_limits, strict=True):
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            row = db.execute(
                "SELECT window_started_at,attempts FROM auth_rate_limits WHERE bucket_hash=?",
                (digest,),
            ).fetchone()
            if row is None or timestamp - row["window_started_at"] >= window_seconds:
                db.execute(
                    "INSERT INTO auth_rate_limits(bucket_hash,window_started_at,attempts) "
                    "VALUES(?,?,1) ON CONFLICT(bucket_hash) DO UPDATE SET "
                    "window_started_at=excluded.window_started_at,attempts=1",
                    (digest, timestamp),
                )
                continue
            if row["attempts"] >= limit:
                retry_after = max(
                    retry_after, row["window_started_at"] + window_seconds - timestamp
                )
                continue
            db.execute(
                "UPDATE auth_rate_limits SET attempts=attempts+1 WHERE bucket_hash=?", (digest,)
            )
        db.execute(
            "DELETE FROM auth_rate_limits WHERE window_started_at < ?",
            (timestamp - max(window_seconds * 2, 3600),),
        )
    if retry_after:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele prób. Spróbuj ponownie później.",
            headers={"Retry-After": str(retry_after)},
        )


def ip_bucket(action: str, address: str) -> str:
    return f"auth:{action}:ip:{address}"


def identity_bucket(action: str, identity: str) -> str:
    return f"auth:{action}:identity:{identity.strip().casefold()}"
