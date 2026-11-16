"""API client tests, including TLS against a real local HTTPS server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import ssl
import threading

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from custom_components.otodo.api import (
    OtodoAPI,
    OtodoAuthError,
    OtodoCertificateError,
    OtodoConnectionError,
    OtodoFingerprintError,
    OtodoHTTPSRequiredError,
    OtodoTLSHandshakeError,
    parse_fingerprint,
)

DIGEST = bytes(range(32))
COLON = ":".join(f"{b:02X}" for b in DIGEST)


@pytest.mark.parametrize(
    "text",
    [
        COLON,  # otodo's startup log
        COLON.lower(),
        f"sha256 Fingerprint={COLON}",  # openssl x509 -fingerprint -sha256
        DIGEST.hex(),
        f"  {COLON}\n",
    ],
)
def test_parse_fingerprint_accepts_common_forms(text: str) -> None:
    assert parse_fingerprint(text) == DIGEST


@pytest.mark.parametrize("text", ["", "abc", COLON[:-3], "zz" * 32, ":".join(["AB"] * 20)])
def test_parse_fingerprint_rejects_garbage(text: str) -> None:
    with pytest.raises(ValueError):
        parse_fingerprint(text)


def _self_signed(tmp: Path) -> tuple[Path, Path, str]:
    """Create a certificate like otodo's generated one; return paths and fingerprint."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "otodo")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(hours=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp / "cert.pem", tmp / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    der = cert.public_bytes(serialization.Encoding.DER)
    fingerprint = ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())
    return cert_path, key_path, fingerprint


class _OtodoHandler(BaseHTTPRequestHandler):
    """Just enough of otodo's API for the client: projects and the event stream."""

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for _ in range(3):
                self.wfile.write(b'data: {"project_id":1}\n\n')
            return
        if self.headers.get("Authorization") != "Bearer otodo_good":
            body, status = {"error": "invalid API key"}, 401
        else:
            body, status = [{"id": 1, "name": "Groceries"}], 200
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


def _serve(ctx: ssl.SSLContext | None) -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), _OtodoHandler)
    if ctx is not None:
        # A failed handshake surfaces as an OSError in accept(), which
        # socketserver drops, like a real server would.
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    return server, thread


@pytest.fixture
def servers(tmp_path: Path, socket_enabled: None) -> Iterator[dict]:
    """An HTTPS server with a self-signed cert and a plain HTTP server.

    Real loopback sockets, so TLS verification and pinning run for real. They
    run on their own thread so a handshake the client rightly aborts is not
    reported as an error on Home Assistant's event loop.
    """
    cert, key, fingerprint = _self_signed(tmp_path)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(cert, key)
    running = [_serve(ctx), _serve(None)]
    (tls, _), (plain, _) = running
    try:
        yield {
            "https": f"https://127.0.0.1:{tls.server_port}",
            "http": f"http://127.0.0.1:{plain.server_port}",
            "https_to_plain": f"https://127.0.0.1:{plain.server_port}",
            "fingerprint": fingerprint,
        }
    finally:
        for server, thread in running:
            server.shutdown()
            server.server_close()
            thread.join()


@pytest.fixture
async def session(socket_enabled: None) -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


async def test_self_signed_rejected_when_verifying(servers: dict, session: aiohttp.ClientSession) -> None:
    api = OtodoAPI(servers["https"], "otodo_good", session)
    with pytest.raises(OtodoCertificateError):
        await api.validate()


async def test_self_signed_accepted_without_verification(servers: dict, session: aiohttp.ClientSession) -> None:
    api = OtodoAPI(servers["https"], "otodo_good", session, verify_ssl=False)
    assert await api.list_projects() == [{"id": 1, "name": "Groceries"}]


async def test_pinned_fingerprint(servers: dict, session: aiohttp.ClientSession) -> None:
    # Pinning trusts the self-signed cert even with verification on.
    api = OtodoAPI(
        servers["https"], "otodo_good", session, fingerprint=servers["fingerprint"]
    )
    await api.validate()

    wrong = OtodoAPI(
        servers["https"], "otodo_good", session, fingerprint=":".join(["00"] * 32)
    )
    with pytest.raises(OtodoFingerprintError):
        await wrong.validate()


async def test_https_url_to_plain_http_server(servers: dict, session: aiohttp.ClientSession) -> None:
    api = OtodoAPI(servers["https_to_plain"], "otodo_good", session)
    with pytest.raises(OtodoTLSHandshakeError):
        await api.validate()


async def test_bad_key_over_tls(servers: dict, session: aiohttp.ClientSession) -> None:
    api = OtodoAPI(servers["https"], "otodo_bad", session, verify_ssl=False)
    with pytest.raises(OtodoAuthError):
        await api.validate()


async def test_events_over_pinned_tls(servers: dict, session: aiohttp.ClientSession) -> None:
    api = OtodoAPI(
        servers["https"], "otodo_good", session, fingerprint=servers["fingerprint"]
    )
    count = 0
    async for _ in api.events():
        count += 1
    assert count == 3


async def test_http_url_to_https_otodo(aioclient_mock) -> None:
    """Go's reply to plain HTTP on a TLS port, which otodo now serves."""
    aioclient_mock.get(
        "http://10.0.0.5:21000/api/projects",
        status=400,
        text="Client sent an HTTP request to an HTTPS server.\n",
    )
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    api = OtodoAPI("http://10.0.0.5:21000", "otodo_good", session)
    with pytest.raises(OtodoHTTPSRequiredError):
        await api.validate()
    await session.close()


async def test_unreachable(servers: dict, session: aiohttp.ClientSession) -> None:
    api = OtodoAPI("http://127.0.0.1:1", "otodo_good", session)
    with pytest.raises(OtodoConnectionError):
        await api.validate()
