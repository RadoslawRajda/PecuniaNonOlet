import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import launcher


@pytest.mark.parametrize("failure", ["interrupt", "startup", "mdns"])
def test_launcher_stops_api_and_mdns(monkeypatch, failure):
    events = []
    monkeypatch.setattr(sys, "argv", ["launcher.py", "--ip", "192.168.1.45"])
    monkeypatch.setattr(launcher, "select_lan_ip", lambda _: "192.168.1.45")
    monkeypatch.setattr(launcher.signal, "signal", lambda *_: None)
    tls_files = SimpleNamespace(
        certificate=Path("server-cert.pem"),
        private_key=Path("server-key.pem"),
        ca_certificate=Path("local-root-ca.cer"),
        ca_fingerprint_sha256="00:11",
    )
    monkeypatch.setattr(launcher, "ensure_local_tls", lambda *_: tls_files)

    class Server:
        should_exit = False

    class Thread:
        def is_alive(self):
            if failure == "interrupt":
                raise KeyboardInterrupt
            return False

        def join(self, timeout):
            events.append(("join", timeout))

    class Mdns:
        def unregister_service(self, _):
            events.append("unregister")

        def close(self):
            events.append("close")

    server = Server()
    bootstrap_server = Server()

    def start(_, tls):
        assert tls is tls_files
        if failure == "startup":
            raise RuntimeError("API nie wystartowało")
        return server, Thread()

    def announce(_):
        if failure == "mdns":
            raise OSError("mDNS unavailable")
        return Mdns(), object()

    monkeypatch.setattr(launcher, "start_api", start)
    monkeypatch.setattr(launcher, "start_bootstrap_http", lambda _: (bootstrap_server, Thread()))
    monkeypatch.setattr(launcher, "announce_service", announce)

    assert launcher.main() == (0 if failure == "interrupt" else 1)
    if failure == "startup":
        assert events == []
    elif failure == "mdns":
        assert events == [("join", 10), ("join", 10)]
        assert server.should_exit
        assert bootstrap_server.should_exit
    else:
        assert events == ["unregister", "close", ("join", 10), ("join", 10)]
        assert server.should_exit
        assert bootstrap_server.should_exit


def test_mdns_registration_failure_closes_socket(monkeypatch):
    events = []

    class FakeZeroconf:
        def register_service(self, _):
            raise OSError("mDNS unavailable")

        def close(self):
            events.append("close")

    monkeypatch.setattr(launcher, "Zeroconf", FakeZeroconf)
    with pytest.raises(OSError):
        launcher.announce_service("192.168.1.45")
    assert events == ["close"]


def test_mdns_service_advertises_https_on_tls_port(monkeypatch):
    captured = {}

    class FakeZeroconf:
        def register_service(self, info):
            captured["info"] = info

        def close(self):
            pass

    monkeypatch.setattr(launcher, "Zeroconf", FakeZeroconf)
    _, info = launcher.announce_service("192.168.1.45")

    assert info.port == launcher.HTTPS_PORT
    assert info.properties[b"scheme"] == b"https"
    assert info.properties[b"path"] == b"/"


def test_start_api_configures_tls_certificate_and_private_key(monkeypatch, tmp_path):
    captured = {}
    tls_files = SimpleNamespace(
        certificate=tmp_path / "server-cert.pem",
        private_key=tmp_path / "server-key.pem",
    )

    class FakeServer:
        should_exit = False

        def __init__(self, config):
            self.config = config
            self.started = False

        def run(self):
            self.started = True

    def fake_config(app, **kwargs):
        captured.update(app=app, **kwargs)
        return kwargs

    monkeypatch.setattr(launcher.uvicorn, "Config", fake_config)
    monkeypatch.setattr(launcher.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)

    server, thread = launcher.start_api("192.168.1.45", tls_files)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert captured["ssl_certfile"] == str(tls_files.certificate)
    assert captured["ssl_keyfile"] == str(tls_files.private_key)
    assert captured["port"] == launcher.HTTPS_PORT
    assert server.started


@pytest.mark.parametrize("path", ["/", "/local-root-ca.cer"])
def test_bootstrap_http_allows_installation_page_and_ca_file(path):
    called = []

    async def application(scope, receive, send):
        called.append(scope["path"])

    app = launcher.BootstrapOnlyApp(application)

    async def run():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_):
            pass

        await app(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            receive,
            send,
        )

    import asyncio

    asyncio.run(run())
    assert called == [path]


@pytest.mark.parametrize("path", ["/api/login", "/docs", "/health", "/api/me"])
def test_bootstrap_http_only_allows_certificate_bootstrap_paths(path):
    called = []

    async def application(scope, receive, send):
        called.append(scope["path"])

    app = launcher.BootstrapOnlyApp(application)

    async def run():
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await app(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            receive,
            send,
        )
        return sent

    import asyncio

    messages = asyncio.run(run())
    assert messages[0]["status"] == 404
    assert called == []
