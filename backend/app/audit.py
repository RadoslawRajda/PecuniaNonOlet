"""Append audit events inside the database transaction they describe."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from typing import Any

_SENSITIVE_KEY = re.compile(r"password|token|secret|authorization|credential|cookie", re.IGNORECASE)


def write_audit_event(
    db: sqlite3.Connection,
    *,
    actor_user_id: int | None,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: Mapping[str, Any],
    created_at: int,
) -> None:
    """Insert a sanitized event; failures intentionally abort the caller's transaction."""
    if any(_SENSITIVE_KEY.search(str(key)) for key in details):
        raise ValueError("Sensitive authentication data cannot be written to the audit log.")
    safe_details = json.dumps(details, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    db.execute(
        """INSERT INTO audit_events(
               actor_user_id, actor_role, action, entity_type, entity_id, details_json, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (actor_user_id, actor_role, action, entity_type, entity_id, safe_details, created_at),
    )
