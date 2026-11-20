import pytest
import requests
from app.adapters.google_oidc import (
    GOOGLE_CERTS_TIMEOUT_SECONDS,
    GOOGLE_CERTS_URL,
    GoogleCertificateRequest,
    _cache_lifetime,
)
from google.auth.exceptions import TransportError


class FakeResponse:
    status_code = 200
    headers = {"Cache-Control": "public, max-age=120"}
    content = b'{"key":"certificate"}'


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_google_certificate_transport_uses_timeout_no_redirect_and_cache():
    adapter = GoogleCertificateRequest()
    session = FakeSession()
    adapter._session = session

    first = adapter(GOOGLE_CERTS_URL)
    second = adapter(GOOGLE_CERTS_URL)

    assert first is second
    assert first.status == 200
    assert first.data == b'{"key":"certificate"}'
    assert len(session.calls) == 1
    assert session.calls[0] == (
        "GET",
        GOOGLE_CERTS_URL,
        {"timeout": GOOGLE_CERTS_TIMEOUT_SECONDS, "allow_redirects": False},
    )


def test_google_certificate_transport_rejects_other_destinations_and_transport_errors():
    adapter = GoogleCertificateRequest()
    with pytest.raises(TransportError):
        adapter("https://attacker.example/certs")

    adapter._session = FakeSession(error=requests.Timeout("timeout"))
    with pytest.raises(TransportError):
        adapter(GOOGLE_CERTS_URL)


def test_google_certificate_cache_honors_no_store_and_bounds_lifetime():
    assert _cache_lifetime({"Cache-Control": "no-store, max-age=60"}) == 0
    assert _cache_lifetime({"Cache-Control": "public, max-age=900000"}) == 21_600

    adapter = GoogleCertificateRequest()
    session = FakeSession()
    session.response.headers = {"Cache-Control": "no-store"}
    adapter._session = session
    adapter(GOOGLE_CERTS_URL)
    adapter(GOOGLE_CERTS_URL)
    assert len(session.calls) == 2
