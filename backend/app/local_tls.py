"""Create a private local CA and a TLS certificate for the mDNS API name."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

MDNS_DNS_NAME = "pecunianonolet.local"
CA_VALIDITY_DAYS = 3650
SERVER_VALIDITY_DAYS = 397
SERVER_RENEWAL_MARGIN = timedelta(days=14)


@dataclass(frozen=True)
class LocalTLSFiles:
    certificate: Path
    private_key: Path
    ca_certificate: Path
    ca_fingerprint_sha256: str


def _write_atomically(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        if os.name != "nt":
            path.chmod(mode)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def _private_key_pem(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_key_bytes(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _new_ca(now: datetime) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    certificate_time = now.astimezone(timezone.utc).replace(tzinfo=None)
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "PecuniaNonOlet Local Development CA")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(certificate_time - timedelta(minutes=5))
        .not_valid_after(certificate_time + timedelta(days=CA_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False
        )
        .sign(private_key, hashes.SHA256())
    )
    return private_key, certificate


def _load_or_create_ca(
    directory: Path, now: datetime
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key_path = directory / "local-root-ca-key.pem"
    certificate_path = directory / "local-root-ca.pem"
    try:
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("Unexpected CA key type")
        if _public_key_bytes(private_key) != certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ):
            raise ValueError("CA key does not match certificate")
        constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
        if not constraints.ca or certificate.not_valid_after_utc <= now + SERVER_RENEWAL_MARGIN:
            raise ValueError("CA certificate is invalid or expiring")
        return private_key, certificate
    except (OSError, ValueError, TypeError, x509.ExtensionNotFound):
        private_key, certificate = _new_ca(now)
        _write_atomically(key_path, _private_key_pem(private_key), mode=0o600)
        _write_atomically(
            certificate_path,
            certificate.public_bytes(serialization.Encoding.PEM),
            mode=0o644,
        )
        _write_atomically(
            directory / "local-root-ca.cer",
            certificate.public_bytes(serialization.Encoding.DER),
            mode=0o644,
        )
        return private_key, certificate


def _valid_server_certificate(
    certificate: x509.Certificate,
    private_key: ec.EllipticCurvePrivateKey,
    ca_certificate: x509.Certificate,
    lan_ip: str,
    now: datetime,
) -> bool:
    try:
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if MDNS_DNS_NAME not in names.get_values_for_type(x509.DNSName):
            return False
        if ipaddress.ip_address(lan_ip) not in names.get_values_for_type(x509.IPAddress):
            return False
        if certificate.issuer != ca_certificate.subject:
            return False
        if certificate.not_valid_after_utc <= now + SERVER_RENEWAL_MARGIN:
            return False
        if certificate.not_valid_before_utc > now:
            return False
        if _public_key_bytes(private_key) != certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ):
            return False
        ca_public_key = ca_certificate.public_key()
        if not isinstance(ca_public_key, ec.EllipticCurvePublicKey):
            return False
        signature_hash_algorithm = certificate.signature_hash_algorithm
        if signature_hash_algorithm is None:
            return False
        ca_public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(signature_hash_algorithm),
        )
        return True
    except (ValueError, TypeError, x509.ExtensionNotFound):
        return False


def _new_server_certificate(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_certificate: x509.Certificate,
    lan_ip: str,
    now: datetime,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    certificate_time = now.astimezone(timezone.utc).replace(tzinfo=None)
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, MDNS_DNS_NAME)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(certificate_time - timedelta(minutes=5))
        .not_valid_after(certificate_time + timedelta(days=SERVER_VALIDITY_DAYS))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(MDNS_DNS_NAME), x509.IPAddress(ipaddress.ip_address(lan_ip))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return private_key, certificate


def ensure_local_tls(directory: Path, lan_ip: str) -> LocalTLSFiles:
    """Return a persistent local CA and a leaf cert valid for mDNS and LAN IP."""
    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    now = datetime.now(timezone.utc)
    ca_key, ca_certificate = _load_or_create_ca(directory, now)
    key_path = directory / "server-key.pem"
    certificate_path = directory / "server-cert.pem"
    try:
        server_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        server_certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        if not isinstance(server_key, ec.EllipticCurvePrivateKey) or not _valid_server_certificate(
            server_certificate, server_key, ca_certificate, lan_ip, now
        ):
            raise ValueError("Server certificate does not match the local CA or host")
    except (OSError, ValueError, TypeError):
        server_key, server_certificate = _new_server_certificate(
            ca_key, ca_certificate, lan_ip, now
        )
        _write_atomically(key_path, _private_key_pem(server_key), mode=0o600)
        _write_atomically(
            certificate_path,
            server_certificate.public_bytes(serialization.Encoding.PEM),
            mode=0o644,
        )

    ca_der = ca_certificate.public_bytes(serialization.Encoding.DER)
    _write_atomically(
        directory / "local-root-ca.cer",
        ca_der,
        mode=0o644,
    )
    fingerprint = hashlib.sha256(ca_der).hexdigest().upper()
    fingerprint = ":".join(
        fingerprint[index : index + 2] for index in range(0, len(fingerprint), 2)
    )
    return LocalTLSFiles(
        certificate=certificate_path,
        private_key=key_path,
        ca_certificate=directory / "local-root-ca.cer",
        ca_fingerprint_sha256=fingerprint,
    )
