"""Shared fixtures for otodo tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
import pytest

from custom_components.otodo.const import CONF_FINGERPRINT, DOMAIN

URL = "https://otodo.example.com"
API_KEY = "otodo_testkey"
ENTRY_DATA = {
    CONF_URL: URL,
    CONF_API_KEY: API_KEY,
    CONF_VERIFY_SSL: True,
    CONF_FINGERPRINT: "",
}
# What otodo logs at startup: "TLS certificate SHA-256 fingerprint: AA:38:..."
FINGERPRINT = ":".join(["AB"] * 32)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components/."""


@pytest.fixture
def mock_validate(aioclient_mock) -> Generator:
    """Patch the connection check the config flow runs.

    Depends on aioclient_mock so the flow's HTTP session is a mock too:
    creating a real one opens a resolver socket, which the test harness
    forbids.
    """
    with patch("custom_components.otodo.api.OtodoAPI.validate") as mock:
        yield mock


def mock_otodo(aioclient_mock, projects: dict[int, tuple[str, list[dict]]], url: str = URL) -> None:
    """Register otodo REST responses: {project_id: (name, [todo, ...])}."""
    aioclient_mock.get(
        f"{url}/api/projects",
        json=[{"id": pid, "name": name} for pid, (name, _) in projects.items()],
    )
    for pid, (_, todos) in projects.items():
        aioclient_mock.get(f"{url}/api/projects/{pid}/todos", json=todos)
    # One event, then the stream ends; the listener backs off before reconnecting.
    aioclient_mock.get(f"{url}/api/events", text='data: {"project_id":0}\n\n')


__all__ = ["API_KEY", "DOMAIN", "ENTRY_DATA", "FINGERPRINT", "URL", "mock_otodo"]
