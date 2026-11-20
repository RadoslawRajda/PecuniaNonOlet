import base64
import sqlite3

import pytest
from app.config import Settings, load_settings
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import ValidationError

PRODUCTION_IDENTITY = {
    "app_env": "production",
    "mfa_encryption_key": base64.urlsafe_b64encode(b"k" * 32).decode(),
    "turnstile_secret_key": "private-turnstile-secret",
    "google_oauth_client_ids": "mobile-client.apps.googleusercontent.com",
    "webauthn_rp_id": "pecunia.example.com",
    "webauthn_allowed_origins": "https://pecunia.example.com",
    "android_sha256_cert_fingerprints": "AA:" * 31 + "AA",
    "trusted_hosts": "pecunia.example.com,api.pecunia.example.com",
}


def test_load_settings_reads_environment_with_typed_secret_and_path(monkeypatch, tmp_path):
    database = tmp_path / "pecunia.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())

    settings = load_settings()

    assert settings.database_path == database
    assert (
        settings.mfa_encryption_key.get_secret_value()
        == base64.urlsafe_b64encode(b"k" * 32).decode()
    )
    assert "kkkk" not in repr(settings)


def test_production_settings_reject_development_configuration():
    with pytest.raises(ValidationError, match="Invalid production configuration"):
        Settings(app_env="production")


def test_production_settings_reject_wildcard_trusted_hosts():
    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        Settings(
            app_env="production",
            mfa_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
            turnstile_secret_key="private-turnstile-secret",
            google_oauth_client_ids="mobile-client.apps.googleusercontent.com",
            webauthn_rp_id="pecunia.example.com",
            webauthn_allowed_origins="https://pecunia.example.com",
            android_sha256_cert_fingerprints="AA:" * 31 + "AA",
            trusted_hosts="*",
        )


def test_production_settings_accept_public_domains_and_private_keys():
    settings = Settings(
        app_env="production",
        mfa_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
        turnstile_secret_key="private-turnstile-secret",
        google_oauth_client_ids="mobile-client.apps.googleusercontent.com",
        webauthn_rp_id="pecunia.example.com",
        webauthn_allowed_origins=(
            "https://pecunia.example.com,android:apk-key-hash:"
            + base64.urlsafe_b64encode(b"a" * 32).decode().rstrip("=")
        ),
        android_sha256_cert_fingerprints="AA:" * 31 + "AA",
        trusted_hosts="pecunia.example.com,api.pecunia.example.com",
    )

    assert settings.app_env == "production"


def test_production_normalizes_identity_lists_once():
    settings = Settings(
        **(
            PRODUCTION_IDENTITY
            | {
                "trusted_hosts": " PECUNIA.EXAMPLE.COM , api.pecunia.example.com , pecunia.example.com ",
                "webauthn_allowed_origins": " https://pecunia.example.com ",
                "google_oauth_client_ids": " mobile-client.apps.googleusercontent.com ",
                "android_sha256_cert_fingerprints": ("aa:" * 31 + "aa"),
                "webauthn_rp_id": " PECUNIA.EXAMPLE.COM ",
            }
        )
    )
    assert settings.trusted_hosts == "pecunia.example.com,api.pecunia.example.com"
    assert settings.webauthn_allowed_origins == "https://pecunia.example.com"
    assert settings.google_oauth_client_ids == "mobile-client.apps.googleusercontent.com"
    assert settings.android_sha256_cert_fingerprints == "AA:" * 31 + "AA"
    assert settings.webauthn_rp_id == "pecunia.example.com"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"android_sha256_cert_fingerprints": Settings().android_sha256_cert_fingerprints},
            "debug certificate",
        ),
        (
            {
                "android_sha256_cert_fingerprints": "AA:" * 31
                + "AA,"
                + Settings().android_sha256_cert_fingerprints
            },
            "debug certificate",
        ),
        ({"android_sha256_cert_fingerprints": "A" * 95}, "SHA-256 fingerprints"),
        (
            {
                "webauthn_allowed_origins": "https://pecunia.example.com,"
                + Settings().webauthn_allowed_origins.split(",")[-1]
            },
            "production origins",
        ),
        ({"webauthn_allowed_origins": "android:apk-key-hash:abc123"}, "production origins"),
        ({"webauthn_allowed_origins": "https://other.example.com"}, "production origins"),
        ({"trusted_hosts": "api.pecunia.example.com,*"}, "TRUSTED_HOSTS"),
        ({"trusted_hosts": "api.pecunia.example.com"}, "association documents"),
        ({"webauthn_allowed_origins": "https://api.pecunia.example.com"}, "RP's HTTPS origin"),
        ({"apple_team_id": "invalid"}, "APPLE_TEAM_ID"),
        ({"ios_bundle_id": "bad bundle"}, "IOS_BUNDLE_ID"),
        ({"android_package_name": "bad-package"}, "Android package name"),
        (
            {"google_oauth_client_ids": "mobile-client.apps.googleusercontent.com,bad"},
            "GOOGLE_OAUTH_CLIENT_IDS",
        ),
    ],
)
def test_production_rejects_invalid_identity_list_entries(overrides, message):
    with pytest.raises(ValidationError, match=message):
        Settings(**(PRODUCTION_IDENTITY | overrides))


def test_app_factory_keeps_injected_settings_on_app_state():
    settings = Settings(app_env="test", lan_ip="192.0.2.10")

    application = create_app(settings)

    assert application.state.settings is settings
    assert "/api/register" in application.openapi()["paths"]


def test_app_factory_uses_injected_database_path(tmp_path):
    database = tmp_path / "injected.db"
    application = create_app(Settings(app_env="test", database_path=database))

    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}

    assert database.is_file()


def test_explicit_instance_settings_override_environment_for_migrations_and_events(
    tmp_path, monkeypatch
):
    environment_db = tmp_path / "environment.db"
    first_db = tmp_path / "first.db"
    second_db = tmp_path / "second.db"
    monkeypatch.setenv("DATABASE_PATH", str(environment_db))
    first = create_app(Settings(app_env="test", database_path=first_db))
    second = create_app(Settings(app_env="test", database_path=second_db))
    registration = {
        "email": "isolated@example.com",
        "password": "violet-bridge-2026!",
        "captcha_token": "test-token",
    }

    with TestClient(first) as first_client, TestClient(second) as second_client:
        assert first_client.post("/api/register", json=registration).status_code == 201
        assert second_client.post("/api/register", json=registration).status_code == 201
        assert (
            first_client.post(
                "/api/login", json={"email": registration["email"], "password": "wrong"}
            ).status_code
            == 401
        )
        assert (
            second_client.post(
                "/api/login", json={"email": registration["email"], "password": "wrong"}
            ).status_code
            == 401
        )

    assert not environment_db.exists()
    for path in (first_db, second_db):
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM auth_rate_limits").fetchone()[0] >= 2
            assert db.execute("SELECT COUNT(*) FROM security_events").fetchone()[0] == 2


def test_production_app_disables_public_docs_and_rejects_unknown_hosts(tmp_path):
    settings = Settings(
        app_env="production",
        database_path=tmp_path / "production.db",
        mfa_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
        turnstile_secret_key="private-turnstile-secret",
        google_oauth_client_ids="mobile-client.apps.googleusercontent.com",
        webauthn_rp_id="pecunia.example.com",
        webauthn_allowed_origins="https://pecunia.example.com",
        android_sha256_cert_fingerprints="AA:" * 31 + "AA",
        trusted_hosts="pecunia.example.com,api.pecunia.example.com",
    )
    application = create_app(settings)

    with TestClient(application) as client:
        assert client.get("/docs", headers={"host": "api.pecunia.example.com"}).status_code == 404
        assert (
            client.get("/openapi.json", headers={"host": "api.pecunia.example.com"}).status_code
            == 404
        )
        assert client.get("/", headers={"host": "api.pecunia.example.com"}).status_code == 404
        assert (
            client.get(
                "/local-root-ca.cer", headers={"host": "api.pecunia.example.com"}
            ).status_code
            == 404
        )
        assert client.get("/health", headers={"host": "attacker.example"}).status_code == 400
        assert client.get("/health", headers={"host": "api.pecunia.example.com"}).status_code == 200
