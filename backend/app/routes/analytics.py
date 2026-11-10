"""Read-only analytics endpoints for users with the analyst role."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.authorization import require_roles
from app.database import connect_db
from app.schemas import User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
Analyst = Annotated[User, Depends(require_roles("analyst"))]
MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807


class Overview(BaseModel):
    users_total: int
    users_by_role: dict[str, int]
    active_sessions: int
    transactions_total: int
    transactions_by_kind: dict[str, int]
    transactions_by_status: dict[str, int]


class AnalystUser(BaseModel):
    id: int
    email: str
    role: Literal["user", "analyst"]
    created_at: str
    accounts_count: int
    transactions_count: int


class UserPage(BaseModel):
    users: list[AnalystUser]
    limit: int
    offset: int
    total: int


class AnalystTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["opening", "transfer", "exchange"]
    status: Literal["completed", "reversed"]
    sender_user_id: int
    sender_email: str
    recipient_user_id: int | None
    recipient_email: str | None
    source_currency_code: str | None
    destination_currency_code: str
    source_amount_minor: int | None
    destination_amount_minor: int
    exchange_rate: str | None
    created_at: str


class TransactionPage(BaseModel):
    transactions: list[AnalystTransaction]
    limit: int
    offset: int
    total: int


class AuditEvent(BaseModel):
    id: int
    actor_user_id: int | None
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, object]
    created_at: str


class AuditEventPage(BaseModel):
    events: list[AuditEvent]
    limit: int
    offset: int
    total: int


def timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/overview", response_model=Overview)
def overview(_: Analyst) -> Overview:
    with closing(connect_db()) as db:
        db.execute("BEGIN")
        users_total = db.execute("SELECT count(*) FROM users").fetchone()[0]
        users_by_role = {
            row["role_name"]: row["total"]
            for row in db.execute(
                "SELECT role_name, count(*) AS total FROM user_roles GROUP BY role_name"
            )
        }
        active_sessions = db.execute(
            "SELECT count(*) FROM sessions WHERE expires_at > unixepoch()"
        ).fetchone()[0]
        transactions_total = db.execute("SELECT count(*) FROM transactions").fetchone()[0]
        transactions_by_kind = {
            row["kind"]: row["total"]
            for row in db.execute("SELECT kind, count(*) AS total FROM transactions GROUP BY kind")
        }
        transactions_by_status = {
            row["status"]: row["total"]
            for row in db.execute("SELECT status, count(*) AS total FROM transactions GROUP BY status")
        }
    return Overview(
        users_total=users_total,
        users_by_role=users_by_role,
        active_sessions=active_sessions,
        transactions_total=transactions_total,
        transactions_by_kind=transactions_by_kind,
        transactions_by_status=transactions_by_status,
    )


@router.get("/users", response_model=UserPage)
def list_users(
    _: Analyst,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    role: Literal["user", "analyst"] | None = None,
) -> UserPage:
    where = "WHERE ur.role_name = ?" if role else ""
    params = (role,) if role else ()
    with closing(connect_db()) as db:
        db.execute("BEGIN")
        total = db.execute(
            f"SELECT count(*) FROM users AS u JOIN user_roles AS ur ON ur.user_id = u.id {where}",
            params,
        ).fetchone()[0]
        rows = db.execute(
            f"""
            SELECT u.id, u.email, ur.role_name, u.created_at,
                   (SELECT count(*) FROM accounts a WHERE a.user_id = u.id) AS accounts_count,
                   (SELECT count(*) FROM transactions t
                    WHERE t.sender_user_id = u.id OR t.recipient_user_id = u.id) AS transactions_count
            FROM users AS u JOIN user_roles AS ur ON ur.user_id = u.id
            {where}
            ORDER BY u.created_at DESC, u.id DESC LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return UserPage(
        users=[
            AnalystUser(
                id=row["id"],
                email=row["email"],
                role=row["role_name"],
                created_at=timestamp(row["created_at"]),
                accounts_count=row["accounts_count"],
                transactions_count=row["transactions_count"],
            )
            for row in rows
        ],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    _: Analyst,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    kind: Literal["opening", "transfer", "exchange"] | None = None,
    status: Literal["completed", "reversed"] | None = None,
    user_id: int | None = Query(default=None, gt=0, le=MAX_SQLITE_INTEGER),
    from_timestamp: int | None = Query(default=None, ge=0, le=MAX_SQLITE_INTEGER, alias="from"),
    to_timestamp: int | None = Query(default=None, ge=0, le=MAX_SQLITE_INTEGER, alias="to"),
) -> TransactionPage:
    filters: list[str] = []
    params: list[int | str] = []
    if kind:
        filters.append("t.kind = ?")
        params.append(kind)
    if status:
        filters.append("t.status = ?")
        params.append(status)
    if user_id is not None:
        filters.append("(t.sender_user_id = ? OR t.recipient_user_id = ?)")
        params.extend((user_id, user_id))
    if from_timestamp is not None:
        filters.append("t.created_at >= ?")
        params.append(from_timestamp)
    if to_timestamp is not None:
        filters.append("t.created_at <= ?")
        params.append(to_timestamp)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    with closing(connect_db()) as db:
        db.execute("BEGIN")
        total = db.execute(f"SELECT count(*) FROM transactions AS t {where}", params).fetchone()[0]
        rows = db.execute(
            f"""
            SELECT t.id, t.kind, t.status, t.sender_user_id, sender.email AS sender_email,
                   t.recipient_user_id, recipient.email AS recipient_email,
                   t.source_currency_code, t.destination_currency_code,
                   t.source_amount_minor, t.destination_amount_minor,
                   t.exchange_rate, t.created_at
            FROM transactions AS t
            JOIN users AS sender ON sender.id = t.sender_user_id
            LEFT JOIN users AS recipient ON recipient.id = t.recipient_user_id
            {where}
            ORDER BY t.created_at DESC, t.id DESC LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return TransactionPage(
        transactions=[
            AnalystTransaction(
                **{**dict(row), "created_at": timestamp(row["created_at"])}
            )
            for row in rows
        ],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get("/audit-events", response_model=AuditEventPage)
def list_audit_events(
    _: Analyst,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    action: str | None = Query(default=None, min_length=1, max_length=64),
    entity_type: str | None = Query(default=None, min_length=1, max_length=32),
    actor_user_id: int | None = Query(default=None, gt=0, le=MAX_SQLITE_INTEGER),
    from_timestamp: int | None = Query(default=None, ge=0, le=MAX_SQLITE_INTEGER, alias="from"),
    to_timestamp: int | None = Query(default=None, ge=0, le=MAX_SQLITE_INTEGER, alias="to"),
) -> AuditEventPage:
    if from_timestamp is not None and to_timestamp is not None and from_timestamp > to_timestamp:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nieprawidłowy zakres czasu.")
    filters: list[str] = []
    params: list[int | str] = []
    for field, value in (
        ("action", action),
        ("entity_type", entity_type),
        ("actor_user_id", actor_user_id),
        ("created_at >=", from_timestamp),
        ("created_at <=", to_timestamp),
    ):
        if value is not None:
            if field in ("action", "entity_type", "actor_user_id"):
                filters.append(f"{field} = ?")
            else:
                filters.append(field + " ?")
            params.append(value)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    with closing(connect_db()) as db:
        db.execute("BEGIN")
        total = db.execute(f"SELECT count(*) FROM audit_events {where}", params).fetchone()[0]
        rows = db.execute(
            f"""SELECT id, actor_user_id, actor_role, action, entity_type, entity_id,
                       details_json, created_at
                FROM audit_events {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
    return AuditEventPage(
        events=[
            AuditEvent(
                id=row["id"],
                actor_user_id=row["actor_user_id"],
                actor_role=row["actor_role"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=json.loads(row["details_json"]),
                created_at=timestamp(row["created_at"]),
            )
            for row in rows
        ],
        limit=limit,
        offset=offset,
        total=total,
    )
