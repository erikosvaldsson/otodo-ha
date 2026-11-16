"""Async client for the otodo REST API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
import re
from typing import Any

import aiohttp

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
# The event stream stays open indefinitely; only bound how long connecting takes.
EVENTS_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=15)


class OtodoError(Exception):
    """Base error for otodo API failures."""


class OtodoConnectionError(OtodoError):
    """The server could not be reached or answered unexpectedly."""


class OtodoAuthError(OtodoError):
    """The API key was rejected."""


class OtodoCertificateError(OtodoConnectionError):
    """The server's TLS certificate could not be verified."""


class OtodoFingerprintError(OtodoConnectionError):
    """The server's certificate does not match the pinned fingerprint."""


class OtodoTLSHandshakeError(OtodoConnectionError):
    """A TLS handshake failed, typically because the server speaks plain HTTP."""


class OtodoHTTPSRequiredError(OtodoConnectionError):
    """An http:// URL reached a server that only speaks HTTPS."""


_HEX = re.compile(r"^[0-9a-f]{64}$")


def parse_fingerprint(value: str) -> bytes:
    """Parse a SHA-256 certificate fingerprint.

    Accepts the colon-separated form otodo logs at startup and `openssl x509
    -fingerprint -sha256` prints (optionally prefixed with "sha256
    Fingerprint="), as well as plain hex. Raises ValueError otherwise.
    """
    text = value.strip().lower()
    if "=" in text:
        text = text.rsplit("=", 1)[1]
    text = re.sub(r"[\s:]", "", text)
    if not _HEX.match(text):
        raise ValueError("expected a SHA-256 fingerprint (64 hex digits)")
    return bytes.fromhex(text)


def ssl_option(verify_ssl: bool, fingerprint: str | None) -> bool | aiohttp.Fingerprint:
    """Return the per-request `ssl` argument for the configured TLS mode.

    A pinned fingerprint trusts exactly that certificate, self-signed or not,
    so it wins over the verify flag.
    """
    if fingerprint:
        return aiohttp.Fingerprint(parse_fingerprint(fingerprint))
    return verify_ssl


class OtodoAPI:
    """Async client for the otodo REST API."""

    def __init__(
        self,
        url: str,
        api_key: str,
        session: aiohttp.ClientSession,
        *,
        verify_ssl: bool = True,
        fingerprint: str | None = None,
    ) -> None:
        self._url = url.strip().rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._session = session
        self._ssl = ssl_option(verify_ssl, fingerprint)

    @contextmanager
    def _translate_errors(self) -> Iterator[None]:
        """Turn aiohttp failures into otodo errors a user can act on."""
        try:
            yield
        except aiohttp.ServerFingerprintMismatch as err:
            raise OtodoFingerprintError(
                "the server's certificate does not match the pinned fingerprint"
            ) from err
        except aiohttp.ClientConnectorCertificateError as err:
            raise OtodoCertificateError(
                f"the server's certificate could not be verified: {err.certificate_error}"
            ) from err
        except aiohttp.ClientSSLError as err:
            raise OtodoTLSHandshakeError(f"TLS handshake failed: {err}") from err
        except aiohttp.ClientResponseError as err:
            raise OtodoConnectionError(f"otodo answered HTTP {err.status}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OtodoConnectionError(f"cannot reach otodo: {err!r}") from err

    async def _check(self, resp: aiohttp.ClientResponse) -> None:
        if resp.status == 401:
            raise OtodoAuthError("the API key was rejected")
        if resp.status == 400 and self._url.startswith("http://"):
            # Go's answer to plain HTTP on a TLS port.
            body = await resp.text(errors="replace")
            if "HTTPS" in body:
                raise OtodoHTTPSRequiredError(
                    "otodo is serving HTTPS; change the URL to https://"
                )
        resp.raise_for_status()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        with self._translate_errors():
            async with self._session.request(
                method,
                f"{self._url}{path}",
                headers=self._headers,
                ssl=self._ssl,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as resp:
                await self._check(resp)
                # Every otodo API response is JSON; an empty body gives None.
                return await resp.json(content_type=None)

    async def list_projects(self) -> list[dict]:
        return await self._request("GET", "/api/projects") or []

    async def list_todos(self, project_id: int) -> list[dict]:
        return await self._request("GET", f"/api/projects/{project_id}/todos") or []

    async def create_todo(self, project_id: int, text: str) -> dict:
        return await self._request(
            "POST", f"/api/projects/{project_id}/todos", json={"text": text}
        )

    async def update_todo(
        self,
        todo_id: int,
        *,
        done: bool | None = None,
        text: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if done is not None:
            payload["done"] = done
        if text is not None:
            payload["text"] = text
        return await self._request("PATCH", f"/api/todos/{todo_id}", json=payload)

    async def delete_todo(self, todo_id: int) -> None:
        await self._request("DELETE", f"/api/todos/{todo_id}")

    async def validate(self) -> None:
        """Check that the server is reachable and the key works; raise otherwise."""
        await self.list_projects()

    async def events(self) -> AsyncIterator[None]:
        """Yield once per change event on otodo's server-sent event stream.

        Returns when the server closes the stream; raises OtodoError on failure.
        """
        with self._translate_errors():
            async with self._session.get(
                f"{self._url}/api/events",
                headers=self._headers,
                ssl=self._ssl,
                timeout=EVENTS_TIMEOUT,
            ) as resp:
                await self._check(resp)
                async for line in resp.content:
                    if line.startswith(b"data:"):
                        yield
