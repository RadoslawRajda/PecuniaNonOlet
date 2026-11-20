"""HTTP adapter for same-currency transfers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.authorization import AuthenticatedSession, current_session, require_roles
from app.schemas import TransferRequest, TransferResponse, User
from app.services.transfers import create_transfer as transfer_funds

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
ActiveSession = Annotated[AuthenticatedSession, Depends(current_session)]


@router.post("/transfers", response_model=TransferResponse, status_code=201)
def create_transfer(
    payload: TransferRequest,
    user: AuthenticatedUser,
    session: ActiveSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> TransferResponse:
    return transfer_funds(payload, user, session.session_id, idempotency_key)
