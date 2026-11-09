import io
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routes.profile_photos import MAX_PROFILE_PHOTO_BYTES, photo_path


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "profile.db"))
    monkeypatch.delenv("PROFILE_PHOTO_DIR", raising=False)
    with TestClient(app) as test_client:
        yield test_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(client, email):
    return client.post(
        "/api/register", json={"email": email, "password": "test-password"}
    ).json()


def image_bytes(*, image_format="PNG", size=(64, 48), metadata=None):
    output = io.BytesIO()
    image = Image.new("RGBA", size, (40, 120, 220, 180))
    if image_format == "JPEG":
        image = image.convert("RGB")
    options = {"pnginfo": metadata} if metadata is not None and image_format == "PNG" else {}
    image.save(output, format=image_format, **options)
    return output.getvalue()


def test_profile_photo_upload_is_authenticated_normalized_and_private(client, tmp_path):
    user = create_user(client, "photo-owner@example.com")
    other = create_user(client, "photo-other@example.com")
    raw = image_bytes()
    upload = client.put(
        "/api/profile/photo",
        headers=auth(user["token"]),
        files={"file": ("arbitrary-name.png", raw, "image/png")},
    )
    assert upload.status_code == 204

    photo = client.get("/api/profile/photo", headers=auth(user["token"]))
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["cache-control"] == "private, no-store"
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert photo.content.startswith(b"\xff\xd8\xff")
    with Image.open(io.BytesIO(photo.content)) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.size == (64, 48)
        assert not decoded.getexif()

    assert client.get("/api/profile/photo", headers=auth(other["token"])).status_code == 404
    assert client.get("/api/profile/photo").status_code == 401

    with sqlite3.connect(tmp_path / "profile.db") as db:
        key = db.execute(
            "SELECT storage_key FROM profile_photos WHERE user_id = ?",
            (user["user"]["id"],),
        ).fetchone()[0]
    stored_path = photo_path(key)
    assert stored_path.parent == (tmp_path / "profile_photos").resolve()
    assert stored_path.read_bytes() == photo.content
    if os.name != "nt":
        assert stored_path.stat().st_mode & 0o077 == 0


def test_profile_photo_upload_ignores_client_filename_and_replaces_old_image(client, tmp_path):
    user = create_user(client, "photo-replace@example.com")
    headers = auth(user["token"])
    assert client.put(
        "/api/profile/photo", headers=headers,
        files={"file": ("../../outside.svg", image_bytes(), "image/svg+xml")},
    ).status_code == 204
    with sqlite3.connect(tmp_path / "profile.db") as db:
        old_key = db.execute("SELECT storage_key FROM profile_photos").fetchone()[0]
    old_path = photo_path(old_key)

    assert client.put(
        "/api/profile/photo", headers=headers,
        files={"file": ("same.jpg", image_bytes(image_format="JPEG", size=(20, 30)), "application/octet-stream")},
    ).status_code == 204
    with sqlite3.connect(tmp_path / "profile.db") as db:
        new_key = db.execute("SELECT storage_key FROM profile_photos").fetchone()[0]
    assert new_key != old_key
    assert not old_path.exists()
    assert photo_path(new_key).exists()


def test_profile_photo_rejects_spoofed_invalid_and_unsupported_images(client):
    user = create_user(client, "photo-invalid@example.com")
    headers = auth(user["token"])
    for filename, content, media_type in (
        ("spoof.png", b"<script>alert(1)</script>", "image/png"),
        ("vector.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
        ("animated.gif", image_bytes(image_format="GIF"), "image/gif"),
    ):
        response = client.put(
            "/api/profile/photo", headers=headers,
            files={"file": (filename, content, media_type)},
        )
        assert response.status_code == 415
    assert client.get("/api/profile/photo", headers=headers).status_code == 404


def test_profile_photo_size_and_dimension_limits(client):
    user = create_user(client, "photo-limits@example.com")
    headers = auth(user["token"])
    oversized = client.put(
        "/api/profile/photo", headers=headers,
        files={"file": ("large.png", b"x" * (MAX_PROFILE_PHOTO_BYTES + 1), "image/png")},
    )
    assert oversized.status_code == 413

    too_wide = client.put(
        "/api/profile/photo", headers=headers,
        files={"file": ("wide.png", image_bytes(size=(8193, 1)), "image/png")},
    )
    assert too_wide.status_code == 415


def test_profile_photo_rejects_oversized_chunked_body_without_content_length(client):
    user = create_user(client, "photo-chunked@example.com")
    boundary = "bounded-upload"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()
    response = client.put(
        "/api/profile/photo",
        headers={**auth(user["token"]), "Content-Type": f"multipart/form-data; boundary={boundary}"},
        content=iter((prefix, b"x" * (MAX_PROFILE_PHOTO_BYTES + 1), suffix)),
    )
    assert response.status_code == 413


def test_profile_photo_requires_one_file_named_file_and_user_role(client):
    user = create_user(client, "photo-shape@example.com")
    headers = auth(user["token"])
    assert client.put(
        "/api/profile/photo", headers=headers,
        files={"other": ("photo.png", image_bytes(), "image/png")},
    ).status_code == 422
    assert client.put(
        "/api/profile/photo", headers=headers,
        files=[("file", ("one.png", image_bytes(), "image/png")), ("file", ("two.png", image_bytes(), "image/png"))],
    ).status_code == 400
    assert client.put(
        "/api/profile/photo",
        files={"file": ("photo.png", image_bytes(), "image/png")},
    ).status_code == 401


def test_profile_photo_delete_is_idempotent_and_removes_private_file(client, tmp_path):
    user = create_user(client, "photo-delete@example.com")
    headers = auth(user["token"])
    assert client.delete("/api/profile/photo", headers=headers).status_code == 204
    assert client.put(
        "/api/profile/photo", headers=headers,
        files={"file": ("photo.png", image_bytes(), "image/png")},
    ).status_code == 204
    with sqlite3.connect(tmp_path / "profile.db") as db:
        key = db.execute("SELECT storage_key FROM profile_photos").fetchone()[0]
    path: Path = photo_path(key)
    assert path.exists()
    assert client.delete("/api/profile/photo", headers=headers).status_code == 204
    assert client.delete("/api/profile/photo", headers=headers).status_code == 204
    assert client.get("/api/profile/photo", headers=headers).status_code == 404
    assert not path.exists()


def test_profile_photo_storage_key_must_be_opaque(client, tmp_path):
    user = create_user(client, "photo-path@example.com")
    with sqlite3.connect(tmp_path / "profile.db") as db:
        db.execute(
            "INSERT INTO profile_photos(user_id, storage_key, size_bytes, updated_at) VALUES (?, ?, 1, 1)",
            (user["user"]["id"], "../" + "a" * 33),
        )
    assert client.get("/api/profile/photo", headers=auth(user["token"])).status_code == 404
