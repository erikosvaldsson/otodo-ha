"""Config flow tests."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.otodo.api import (
    OtodoAuthError,
    OtodoCertificateError,
    OtodoConnectionError,
    OtodoFingerprintError,
    OtodoHTTPSRequiredError,
    OtodoTLSHandshakeError,
)
from custom_components.otodo.const import CONF_FINGERPRINT, DOMAIN

from .conftest import API_KEY, ENTRY_DATA, FINGERPRINT, URL


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_validate) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: f" {URL}/ ", CONF_API_KEY: API_KEY, CONF_VERIFY_SSL: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA  # URL trimmed, fingerprint key present
    assert result["result"].unique_id == URL


async def test_user_flow_with_fingerprint(hass: HomeAssistant, mock_validate) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: "https://10.0.0.5:21000",
            CONF_API_KEY: API_KEY,
            CONF_VERIFY_SSL: True,
            CONF_FINGERPRINT: FINGERPRINT,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FINGERPRINT] == FINGERPRINT


@pytest.mark.parametrize(
    ("exc", "errors"),
    [
        (OtodoAuthError, {"base": "invalid_auth"}),
        (OtodoHTTPSRequiredError, {CONF_URL: "https_required"}),
        (OtodoCertificateError, {"base": "certificate_untrusted"}),
        (OtodoFingerprintError, {CONF_FINGERPRINT: "fingerprint_mismatch"}),
        (OtodoTLSHandshakeError, {"base": "tls_handshake"}),
        (OtodoConnectionError, {"base": "cannot_connect"}),
        (RuntimeError, {"base": "unknown"}),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, mock_validate, exc, errors
) -> None:
    result = await _start(hass)
    mock_validate.side_effect = exc("boom")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors

    mock_validate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_rejects_malformed_fingerprint(hass: HomeAssistant, mock_validate) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: URL, CONF_API_KEY: API_KEY, CONF_FINGERPRINT: "not-a-fingerprint"},
    )
    assert result["errors"] == {CONF_FINGERPRINT: "invalid_fingerprint"}
    mock_validate.assert_not_called()


async def test_user_flow_aborts_on_duplicate(hass: HomeAssistant, mock_validate) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=URL, data=ENTRY_DATA).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_moves_to_https_with_pinned_cert(
    hass: HomeAssistant, mock_validate
) -> None:
    """The upgrade path: an entry made for http:// switches to https:// + pin."""
    old = {CONF_URL: "http://10.0.0.5:21000", CONF_API_KEY: API_KEY}  # pre-HTTPS entry
    entry = MockConfigEntry(domain=DOMAIN, unique_id=old[CONF_URL], data=old)
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new = {
        CONF_URL: "https://10.0.0.5:21000",
        CONF_API_KEY: API_KEY,
        CONF_VERIFY_SSL: True,
        CONF_FINGERPRINT: FINGERPRINT,
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dict(entry.data) == new
    assert entry.unique_id == new[CONF_URL]

    # Clearing the fingerprint must remove it, not keep the old one.
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: new[CONF_URL], CONF_API_KEY: API_KEY, CONF_VERIFY_SSL: False},
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_FINGERPRINT] == ""
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_reconfigure_refuses_url_of_other_entry(hass: HomeAssistant, mock_validate) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="https://other", data=ENTRY_DATA).add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=URL, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "https://other", CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_URL] == URL


async def test_reauth_replaces_key(hass: HomeAssistant, mock_validate) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=URL, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_validate.side_effect = OtodoAuthError("nope")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "otodo_wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_validate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "otodo_new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "otodo_new"
    assert entry.data[CONF_URL] == URL
