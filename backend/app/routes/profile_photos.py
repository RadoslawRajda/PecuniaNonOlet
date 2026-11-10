"""Private, normalized profile photo storage."""

from __future__ import annotations

import io
import os
import re
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.responses import JSONResponse

from app.authorization import require_roles
from app.database import connect_db, database_path
from app.schemas import User

router = APIRouter(prefix="/api/profile/photo")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PROFILE_PHOTO_REQUEST_BYTES = MAX_PROFILE_PHOTO_BYTES + 64 * 1024
MAX_PROFILE_PHOTO_PIXELS = 20_000_000
MAX_PROFILE_PHOTO_DIMENSION = 8_192
MAX_STORED_DIMENSION = 1_024
STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.jpg$")
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")


class ProfilePhotoBodyLimitMiddleware:
    """Reject oversized requests without buffering their multipart bodies."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "PUT"
            or scope.get("path") != "/api/profile/photo"
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_PROFILE_PHOTO_REQUEST_BYTES:
                    await JSONResponse(
                        {"detail": "Zdjęcie przekracza dozwolony rozmiar."},
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )(scope, receive, send)
                    return
            except ValueError:
                pass

        with tempfile.SpooledTemporaryFile(max_size=512 * 1024, mode="w+b") as body_file:
            total_bytes = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] == "http.request":
                    body = message.get("body", b"")
                    total_bytes += len(body)
                    if total_bytes > MAX_PROFILE_PHOTO_REQUEST_BYTES:
                        await JSONResponse(
                            {"detail": "Zdjęcie przekracza dozwolony rozmiar."},
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        )(scope, receive, send)
                        return
                    body_file.write(body)
                    if not message.get("more_body", False):
                        break

            body_file.seek(0)

            async def buffered_receive() -> dict[str, Any]:
                chunk = body_file.read(64 * 1024)
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": body_file.tell() < total_bytes,
                }

            await self.app(scope, buffered_receive, send)


def profile_photo_directory() -> Path:
    configured = os.getenv("PROFILE_PHOTO_DIR")
    directory = Path(configured) if configured else database_path().parent / "profile_photos"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    resolved = directory.resolve()
    if not resolved.is_dir():
        raise RuntimeError("Profile photo storage is not a directory")
    if os.name != "nt":
        os.chmod(resolved, 0o700)
    return resolved


def photo_path(storage_key: str) -> Path:
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia profilowego.")
    return profile_photo_directory() / storage_key


def normalize_profile_photo(content: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(content), formats=ALLOWED_IMAGE_FORMATS) as source:
            if source.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("Unsupported image format")
            if source.width > MAX_PROFILE_PHOTO_DIMENSION or source.height > MAX_PROFILE_PHOTO_DIMENSION:
                raise ValueError("Image dimensions exceed the limit")
            if source.width * source.height > MAX_PROFILE_PHOTO_PIXELS:
                raise ValueError("Image pixel count exceeds the limit")
            if getattr(source, "is_animated", False):
                raise ValueError("Animated images are not supported")
            source.verify()

        with Image.open(io.BytesIO(content), formats=ALLOWED_IMAGE_FORMATS) as source:
            oriented = ImageOps.exif_transpose(source)
            oriented.thumbnail(
                (MAX_STORED_DIMENSION, MAX_STORED_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            rgba = oriented.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            output = io.BytesIO()
            background.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Plik musi być poprawnym obrazem JPEG, PNG lub WebP o dozwolonym rozmiarze.",
        ) from exc


def store_photo(user_id: int, photo_bytes: bytes) -> None:
    directory = profile_photo_directory()
    storage_key = f"{uuid.uuid4().hex}.jpg"
    target = directory / storage_key
    old_key: str | None = None
    temporary_path: Path | None = None
    committed = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".upload-", suffix=".tmp", dir=directory, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(photo_bytes)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None

        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT storage_key FROM profile_photos WHERE user_id = ?", (user_id,)
            ).fetchone()
            old_key = current["storage_key"] if current is not None else None
            db.execute(
                """INSERT INTO profile_photos(user_id, storage_key, size_bytes, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       storage_key = excluded.storage_key,
                       size_bytes = excluded.size_bytes,
                       updated_at = excluded.updated_at""",
                (user_id, storage_key, len(photo_bytes), int(time.time())),
            )
        committed = True
        if old_key and old_key != storage_key and STORAGE_KEY_PATTERN.fullmatch(old_key):
            try:
                photo_path(old_key).unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        if not committed:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@router.put(
    "",
    status_code=204,
    response_class=Response,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
    responses={
        401: {"description": "Brak aktywnej sesji."},
        403: {"description": "Operacja dostępna tylko dla zwykłego użytkownika."},
        413: {"description": "Zdjęcie przekracza limit rozmiaru."},
        415: {"description": "Nieobsługiwany lub niepoprawny format obrazu."},
        422: {"description": "Wymagane jest jedno pole pliku o nazwie `file`."},
    },
)
async def upload_profile_photo(request: Request, user: AuthenticatedUser) -> Response:
    async with request.form(
        max_files=1,
        max_fields=0,
        max_part_size=MAX_PROFILE_PHOTO_BYTES,
    ) as form:
        items = form.multi_items()
        if len(items) != 1 or items[0][0] != "file" or not isinstance(items[0][1], UploadFile):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Prześlij jedno zdjęcie w polu `file`.")
        content = await items[0][1].read(MAX_PROFILE_PHOTO_BYTES + 1)
        if len(content) > MAX_PROFILE_PHOTO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Zdjęcie przekracza limit 2 MiB.")
    normalized = await run_in_threadpool(normalize_profile_photo, content)
    await run_in_threadpool(store_photo, user.id, normalized)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_class=Response, include_in_schema=True)
def get_profile_photo(user: AuthenticatedUser) -> Response:
    with closing(connect_db()) as db:
        row = db.execute(
            "SELECT storage_key FROM profile_photos WHERE user_id = ?", (user.id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ustawiono zdjęcia profilowego.")
    try:
        image_bytes = photo_path(row["storage_key"]).read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia profilowego.") from exc
    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline; filename=profile.jpg",
        },
    )


@router.delete("", status_code=204, response_class=Response)
def delete_profile_photo(user: AuthenticatedUser) -> Response:
    storage_key: str | None = None
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT storage_key FROM profile_photos WHERE user_id = ?", (user.id,)
        ).fetchone()
        if row is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        storage_key = row["storage_key"]
        db.execute("DELETE FROM profile_photos WHERE user_id = ?", (user.id,))
    if storage_key:
        photo_path(storage_key).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
