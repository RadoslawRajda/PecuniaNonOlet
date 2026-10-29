import sys

import pytest

import launcher


@pytest.mark.parametrize("failure", ["interrupt", "startup", "mdns"])
def test_launcher_stops_api_and_mdns(monkeypatch, failure):
    events = []
    monkeypatch.setattr(sys, "argv", ["launcher.py", "--ip", "192.168.1.45"])
    monkeypatch.setattr(launcher, "select_lan_ip", lambda _: "192.168.1.45")
    monkeypatch.setattr(launcher.signal, "signal", lambda *_: None)

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

    def start(_):
        if failure == "startup":
            raise RuntimeError("API nie wystartowało")
        return server, Thread()

    def announce(_):
        if failure == "mdns":
            raise OSError("mDNS unavailable")
        return Mdns(), object()

    monkeypatch.setattr(launcher, "start_api", start)
    monkeypatch.setattr(launcher, "announce_service", announce)

    assert launcher.main() == (0 if failure == "interrupt" else 1)
    if failure == "startup":
        assert events == []
    elif failure == "mdns":
        assert events == [("join", 10)]
        assert server.should_exit
    else:
        assert events == ["unregister", "close", ("join", 10)]
        assert server.should_exit


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
