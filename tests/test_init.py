"""Setup, coordinator and todo entity tests."""

from __future__ import annotations

from http import HTTPStatus

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_API_KEY,
    CONF_URL,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.otodo.const import DOMAIN

from .conftest import ENTRY_DATA, URL, mock_otodo

MILK = {"id": 1, "project_id": 7, "text": "milk", "done": False}
EGGS = {"id": 2, "project_id": 7, "text": "eggs", "done": True}


async def _setup(hass: HomeAssistant, data: dict = ENTRY_DATA) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=data[CONF_URL], data=data)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_todo_lists(hass: HomeAssistant, aioclient_mock) -> None:
    mock_otodo(aioclient_mock, {7: ("Groceries", [MILK, EGGS]), 8: ("Work", [])})
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get("todo.groceries")
    assert state is not None
    assert state.state == "1"  # open items
    assert hass.states.get("todo.work").state == "0"

    registry = er.async_get(hass)
    assert registry.async_get("todo.groceries").unique_id == f"{entry.entry_id}_7"

    # Requests carry the API key.
    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert headers["Authorization"] == "Bearer otodo_testkey"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_entry_from_before_https_support_still_loads(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Entries created by 1.0.x have only url and api_key."""
    old = {CONF_URL: "http://10.0.0.5:21000", CONF_API_KEY: "otodo_testkey"}
    mock_otodo(aioclient_mock, {7: ("Groceries", [MILK])}, url=old[CONF_URL])
    entry = await _setup(hass, old)
    assert entry.state is ConfigEntryState.LOADED


async def test_new_renamed_and_deleted_projects(hass: HomeAssistant, aioclient_mock) -> None:
    mock_otodo(aioclient_mock, {7: ("Groceries", [MILK])})
    entry = await _setup(hass)
    coordinator = entry.runtime_data.coordinator

    # Refresh directly: scheduled refreshes run as background tasks, which
    # async_block_till_done does not wait for.
    aioclient_mock.clear_requests()
    mock_otodo(aioclient_mock, {7: ("Food", [MILK]), 9: ("Garden", [])})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # A project created after setup gets an entity without a reload.
    assert hass.states.get("todo.garden") is not None
    # A rename updates the friendly name (the entity id stays).
    assert hass.states.get("todo.groceries").attributes["friendly_name"] == "Food"

    aioclient_mock.clear_requests()
    mock_otodo(aioclient_mock, {9: ("Garden", [])})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("todo.groceries").state == STATE_UNAVAILABLE


async def test_rejected_key_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{URL}/api/projects", status=HTTPStatus.UNAUTHORIZED)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unreachable_server_retries(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{URL}/api/projects", status=HTTPStatus.BAD_GATEWAY)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_todo_actions(hass: HomeAssistant, aioclient_mock) -> None:
    mock_otodo(aioclient_mock, {7: ("Groceries", [MILK])})
    aioclient_mock.post(f"{URL}/api/projects/7/todos", json={**MILK, "id": 3})
    aioclient_mock.patch(f"{URL}/api/todos/1", json={**MILK, "done": True})
    aioclient_mock.delete(f"{URL}/api/todos/1", json={"status": "deleted"})
    await _setup(hass)

    async def call(service: str, data: dict) -> None:
        await hass.services.async_call(
            TODO_DOMAIN, service, {ATTR_ENTITY_ID: "todo.groceries", **data}, blocking=True
        )

    def sent(method: str, path: str):
        return [
            d
            for m, u, d, _ in aioclient_mock.mock_calls
            if m.lower() == method and u.path == path
        ]

    await call("add_item", {"item": "bread"})
    assert sent("post", "/api/projects/7/todos") == [{"text": "bread"}]

    await call("update_item", {"item": "milk", "status": "completed"})
    assert sent("patch", "/api/todos/1")[-1] == {"done": True, "text": "milk"}

    await call("remove_item", {"item": "milk"})
    assert len(sent("delete", "/api/todos/1")) == 1


async def test_todo_action_failure_is_reported(hass: HomeAssistant, aioclient_mock) -> None:
    mock_otodo(aioclient_mock, {7: ("Groceries", [MILK])})
    aioclient_mock.post(f"{URL}/api/projects/7/todos", status=HTTPStatus.INTERNAL_SERVER_ERROR)
    await _setup(hass)

    with pytest.raises(HomeAssistantError, match="otodo"):
        await hass.services.async_call(
            TODO_DOMAIN,
            "add_item",
            {ATTR_ENTITY_ID: "todo.groceries", "item": "bread"},
            blocking=True,
        )
