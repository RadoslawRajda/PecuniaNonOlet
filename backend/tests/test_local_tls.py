import ipaddress
import os
import ssl

from app.local_tls import MDNS_DNS_NAME, ensure_local_tls
from cryptography import x509


def test_local_certificates_are_persistent_and_cover_mdns_and_lan_ip(tmp_path):
    first = ensure_local_tls(tmp_path, "192.168.1.45")
    server_certificate = x509.load_pem_x509_certificate(first.certificate.read_bytes())
    names = server_certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert MDNS_DNS_NAME in names.get_values_for_type(x509.DNSName)
    assert ipaddress.ip_address("192.168.1.45") in names.get_values_for_type(x509.IPAddress)
    assert first.ca_certificate.exists()
    assert len(first.ca_fingerprint_sha256.split(":")) == 32
    if os.name != "nt":
        assert first.private_key.stat().st_mode & 0o777 == 0o600
        assert (tmp_path.stat().st_mode & 0o777) == 0o700

    second = ensure_local_tls(tmp_path, "192.168.1.45")
    assert second == first

    changed_address = ensure_local_tls(tmp_path, "192.168.1.46")
    renewed_certificate = x509.load_pem_x509_certificate(changed_address.certificate.read_bytes())
    renewed_names = renewed_certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    assert ipaddress.ip_address("192.168.1.46") in renewed_names.get_values_for_type(x509.IPAddress)
    assert changed_address.ca_fingerprint_sha256 == first.ca_fingerprint_sha256


def test_generated_https_certificate_validates_for_mdns_host(tmp_path):
    tls_files = ensure_local_tls(tmp_path, "127.0.0.1")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(
        certfile=str(tls_files.certificate), keyfile=str(tls_files.private_key)
    )
    client_context = ssl.create_default_context(cafile=str(tmp_path / "local-root-ca.pem"))
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(
        client_in, client_out, server_side=False, server_hostname=MDNS_DNS_NAME
    )
    server = server_context.wrap_bio(server_in, server_out, server_side=True)

    def transfer(source, destination):
        encrypted = source.read()
        if encrypted:
            destination.write(encrypted)

    client_ready = server_ready = False
    for _ in range(10):
        if not client_ready:
            try:
                client.do_handshake()
                client_ready = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
        transfer(client_out, server_in)
        if not server_ready:
            try:
                server.do_handshake()
                server_ready = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
        transfer(server_out, client_in)
        if client_ready and server_ready:
            break

    assert client_ready and server_ready
    client.write(b"GET /health HTTP/1.1\r\nHost: pecunianonolet.local\r\n\r\n")
    transfer(client_out, server_in)
    request = server.read(4096)
    assert b"GET /health" in request
    server.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    transfer(server_out, client_in)
    response = client.read(4096)

    assert b"200 OK" in response
    assert response.endswith(b"ok")
