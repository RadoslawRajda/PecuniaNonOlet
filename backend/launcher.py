"""Run FastAPI and advertise it on the local network via mDNS."""

from __future__ import annotations

import argparse
import ipaddress
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

import psutil
import uvicorn
from starlette.responses import PlainTextResponse
from zeroconf import ServiceInfo, Zeroconf
from uvicorn.config import Config

from app.local_tls import LocalTLSFiles, ensure_local_tls


PROJECT_ROOT = Path(__file__).resolve().parent
SERVICE_TYPE = "_pecunianonolet._tcp.local."
SERVICE_NAME = "Pecunianonolet API." + SERVICE_TYPE
MDNS_HOSTNAME = "pecunianonolet.local."
HTTPS_PORT = 8000
BOOTSTRAP_HTTP_PORT = 8001


class BootstrapOnlyApp:
    """Expose only the installation page and public CA file on bootstrap HTTP."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (
            scope.get("method") != "GET"
            or scope.get("path") not in {"/", "/local-root-ca.cer"}
        ):
            response = PlainTextResponse("Not Found", status_code=404)
            await response(scope, receive, send)
            return
        await self.application(scope, receive, send)

SKIP_INTERFACES = (
    "docker",
    "veth",
    "br-",
    "virbr",
    "loopback",
    "tailscale",
    "zerotier",
    "vethernet",
    "wsl",
    "vmware",
    "virtualbox",
)


def interrupt_handler(*_: object) -> None:
    raise KeyboardInterrupt


def local_addresses() -> list[tuple[str, str]]:
    """Zwraca lokalne adresy IPv4 aktywnych fizycznych interfejsów."""
    candidates = []
    seen = set()
    # W niektórych środowiskach /proc jest ograniczone; nadal można
    # odczytać listę adresów z net_if_addrs().
    try:
        stats = psutil.net_if_stats()
    except OSError:
        stats = {}

    try:
        interfaces = psutil.net_if_addrs()
    except OSError as exc:
        raise ValueError(
            "System odmówił dostępu do listy interfejsów sieciowych. "
            "Podaj adres ręcznie: --ip 192.168.x.x"
        ) from exc

    for interface, entries in interfaces.items():
        lower_name = interface.lower()
        if any(part in lower_name for part in SKIP_INTERFACES):
            continue
        if stats and (not stats.get(interface) or not stats[interface].isup):
            continue
        for entry in entries:
            if entry.family != socket.AF_INET:
                continue
            try:
                addr = ipaddress.IPv4Address(entry.address)
            except ipaddress.AddressValueError:
                continue
            if (
                not addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_unspecified
                or entry.address in seen
            ):
                continue
            seen.add(entry.address)
            candidates.append((interface, entry.address))

    def preference(item: tuple[str, str]) -> tuple[int, str]:
        name = item[0].lower()
        if any(part in name for part in ("wi-fi", "wifi", "wlan", "wlp", "airport", "en0")):
            return (0, name)
        if any(part in name for part in ("ethernet", "eth", "enp", "eno")):
            return (1, name)
        return (2, name)

    return sorted(candidates, key=preference)


def select_lan_ip(override: str | None) -> str:
    if override:
        try:
            address = ipaddress.IPv4Address(override)
        except ipaddress.AddressValueError as exc:
            raise ValueError("Podany adres --ip nie jest poprawnym IPv4.") from exc
        if not address.is_private or address.is_loopback or address.is_unspecified:
            raise ValueError("Podaj lokalny adres IPv4 komputera (np. 192.168.x.x).")
        return override

    candidates = local_addresses()
    if not candidates:
        raise ValueError(
            "Brak aktywnego prywatnego adresu IPv4. Połącz komputer z Wi-Fi/hotspotem "
            "i uruchom ponownie. Możesz też podać --ip ADRES."
        )

    if len(candidates) == 1:
        interface, ip = candidates[0]
        print(f"Znaleziono sieć: {interface} ({ip})")
        return ip

    print("\nWykryto kilka interfejsów sieciowych:")
    for index, (interface, ip) in enumerate(candidates, start=1):
        print(f"  {index}. {interface} — {ip}")
    print("Wybierz sieć, do której podłączony jest telefon.")
    try:
        choice = input("Numer [1]: ").strip() or "1"
    except EOFError:
        choice = "1"
    try:
        selected = int(choice) - 1
        return candidates[selected][1] if 0 <= selected < len(candidates) else candidates[0][1]
    except ValueError:
        return candidates[0][1]


def start_api(ip: str, tls_files: LocalTLSFiles) -> tuple[uvicorn.Server, threading.Thread]:
    os.environ["LAN_IP"] = ip
    os.environ["DATABASE_PATH"] = str(PROJECT_ROOT / "data" / "pecunia.db")
    config = uvicorn.Config(
        "app.main:app",
        host=ip,
        port=HTTPS_PORT,
        ssl_certfile=str(tls_files.certificate),
        ssl_keyfile=str(tls_files.private_key),
        proxy_headers=False,
        access_log=False,
        timeout_keep_alive=5,
        limit_concurrency=50,
    )
    server = uvicorn.Server(config)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            server.run()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, name="fastapi", daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return server, thread
        if not thread.is_alive():
            reason = str(errors[0]) if errors else "proces serwera zakończył się"
            raise RuntimeError(f"FastAPI nie wystartowało: {reason}. Czy port 8000 jest wolny?")
        time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=5)
    raise RuntimeError("FastAPI nie wystartowało w ciągu 10 sekund.")


def start_bootstrap_http(ip: str) -> tuple[uvicorn.Server, threading.Thread]:
    """Serve only the CA installation page and public CA file over HTTP."""
    from app.main import app

    config = Config(
        BootstrapOnlyApp(app),
        host=ip,
        port=BOOTSTRAP_HTTP_PORT,
        proxy_headers=False,
        access_log=False,
        timeout_keep_alive=5,
        limit_concurrency=10,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            server.run()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, name="http-ca-bootstrap", daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return server, thread
        if not thread.is_alive():
            reason = str(errors[0]) if errors else "proces serwera zakończył się"
            raise RuntimeError(f"HTTP bootstrap nie wystartował: {reason}.")
        time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=5)
    raise RuntimeError("HTTP bootstrap nie wystartował w ciągu 10 sekund.")


def announce_service(ip: str) -> tuple[Zeroconf, ServiceInfo]:
    info = ServiceInfo(
        SERVICE_TYPE,
        SERVICE_NAME,
        addresses=[socket.inet_aton(ip)],
        port=HTTPS_PORT,
        properties={"path": "/", "scheme": "https", "app": "pecunianonolet"},
        server=MDNS_HOSTNAME,
    )
    zeroconf = Zeroconf()
    try:
        zeroconf.register_service(info)
        print("\nmDNS działa i ogłasza usługę w lokalnej sieci.")
        print(f"  Nazwa usługi: {SERVICE_TYPE}")
        print(f"  Nazwa hosta:  {MDNS_HOSTNAME}")
        print(f"  Protokół:     HTTPS na porcie {HTTPS_PORT}")
        print("\nCtrl+C zatrzyma backend i mDNS.\n")
        return zeroconf, info
    except BaseException:
        zeroconf.close()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="PecuniaNonOlet backend LAN")
    parser.add_argument("--ip", help="Wybierz ręcznie istniejący adres IPv4 komputera")
    args = parser.parse_args()

    print("=== PECUNIANONOLET BACKEND ===")
    server = None
    thread = None
    mdns = None
    exit_code = 0
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupt_handler)
    try:
        ip = select_lan_ip(args.ip)
        tls_files = ensure_local_tls(PROJECT_ROOT / "data" / "tls", ip)
        server, thread = start_api(ip, tls_files)
        bootstrap_server, bootstrap_thread = start_bootstrap_http(ip)
        servers = [(server, thread), (bootstrap_server, bootstrap_thread)]
        print(f"  Instalacja certyfikatu (tylko strona i plik): http://{ip}:{BOOTSTRAP_HTTP_PORT}/")
        print(f"  Diagnostyka: https://{MDNS_HOSTNAME.rstrip('.')}:{HTTPS_PORT}/")
        print(f"  Dokumentacja: https://{MDNS_HOSTNAME.rstrip('.')}:{HTTPS_PORT}/docs")
        print(f"  Certyfikat CA dla telefonu: {tls_files.ca_certificate}")
        print(f"  Odcisk SHA-256 CA: {tls_files.ca_fingerprint_sha256}")
        print("  Zainstaluj ten CA na telefonie i zweryfikuj odcisk przed zaufaniem.")
        mdns = announce_service(ip)
        while any(worker.is_alive() for _, worker in servers):
            for _, worker in servers:
                worker.join(timeout=0.5)
        if any(not instance.should_exit for instance, _ in servers):
            raise RuntimeError("Serwer FastAPI zakończył działanie.")
    except KeyboardInterrupt:
        print("\nZatrzymywanie...")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"\nBŁĄD: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        try:
            if mdns is not None:
                zeroconf, info = mdns
                try:
                    zeroconf.unregister_service(info)
                finally:
                    zeroconf.close()
        finally:
            if server is not None and thread is not None:
                server.should_exit = True
                thread.join(timeout=10)
            if "bootstrap_server" in locals() and "bootstrap_thread" in locals():
                bootstrap_server.should_exit = True
                bootstrap_thread.join(timeout=10)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
