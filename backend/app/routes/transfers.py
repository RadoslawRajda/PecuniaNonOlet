"""HTTP adapter for same-currency transfers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.authorization import AuthenticatedSession, current_session, require_roles
from app.rate_limits import client_ip, enforce_rate_limit, identity_bucket, ip_bucket
from app.schemas import TransferRequest, TransferResponse, User
from app.services.transfers import create_transfer as transfer_funds

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
ActiveSession = Annotated[AuthenticatedSession, Depends(current_session)]


@router.post(
    "/transfers",
    response_model=TransferResponse,
    status_code=201,
    summary="Przelej środki na konto innego użytkownika",
    description=(
        "Kwota jest podawana w najmniejszych jednostkach waluty. Źródłowy rachunek musi "
        "należeć do bieżącego użytkownika. `Idempotency-Key` zapobiega powtórnemu "
        "zaksięgowaniu tego samego żądania; inna treść z tym samym kluczem daje 409."
    ),
)
def create_transfer(
    payload: TransferRequest,
    user: AuthenticatedUser,
    session: ActiveSession,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> TransferResponse:
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit(
        [ip_bucket("transfer", address), identity_bucket("transfer", str(user.id))],
        limits=[60, 30],
    )
    return transfer_funds(payload, user, session.session_id, idempotency_key)
