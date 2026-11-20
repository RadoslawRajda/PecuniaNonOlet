"""Private, normalized profile photo storage."""

from __future__ import annotations

import io
import os
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.authorization import require_roles
from app.database import connect_db
from app.photo_storage import STORAGE_KEY_PATTERN, photo_path, profile_photo_directory
from app.schemas import User

router = APIRouter(prefix="/api/profile/photo")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PROFILE_PHOTO_PIXELS = 20_000_000
MAX_PROFILE_PHOTO_DIMENSION = 8_192
MAX_STORED_DIMENSION = 1_024
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")


def normalize_profile_photo(content: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(content), formats=ALLOWED_IMAGE_FORMATS) as source:
            if source.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("Unsupported image format")
            if (
                source.width > MAX_PROFILE_PHOTO_DIMENSION
                or source.height > MAX_PROFILE_PHOTO_DIMENSION
            ):
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
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Prześlij jedno zdjęcie w polu `file`."
            )
        content = await items[0][1].read(MAX_PROFILE_PHOTO_BYTES + 1)
        if len(content) > MAX_PROFILE_PHOTO_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, "Zdjęcie przekracza limit 2 MiB."
            )
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
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia profilowego."
        ) from exc
    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline; filename=profile.jpg",
        },
    )


@router.get("/recipient", response_class=Response)
def get_recipient_photo(
    user: AuthenticatedUser,
    email: str = Query(min_length=3, max_length=254),
) -> Response:
    """Return a recipient photo when available; missing users and photos look identical."""
    with closing(connect_db()) as db:
        row = db.execute(
            """SELECT p.storage_key FROM users AS u
               JOIN profile_photos AS p ON p.user_id = u.id
               WHERE u.email = ? AND u.id != ?""",
            (email.strip().lower(), user.id),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zdjęcie niedostępne.")
    try:
        content = photo_path(row["storage_key"]).read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zdjęcie niedostępne.") from exc
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
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
