"""Todo platform for otodo integration."""

from __future__ import annotations

import logging

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .api import OtodoAPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        [
            OtodoTodoList(data.coordinator, data.api, project_id, entry.entry_id)
            for project_id in data.coordinator.data
        ],
    )


class OtodoTodoList(CoordinatorEntity, TodoListEntity):
    """A single otodo project as a HA todo list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[int, dict]],
        api: OtodoAPI,
        project_id: int,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._project_id = project_id
        self._attr_name = coordinator.data[project_id]["name"]
        self._attr_unique_id = f"{entry_id}_{project_id}"
        self._update_items()

    def _update_items(self) -> None:
        project_data = self.coordinator.data.get(self._project_id, {})
        self._attr_todo_items = [
            TodoItem(
                uid=str(t["id"]),
                summary=t["text"],
                status=(
                    TodoItemStatus.COMPLETED if t["done"] else TodoItemStatus.NEEDS_ACTION
                ),
            )
            for t in project_data.get("todos", [])
        ]

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_items()
        self.async_write_ha_state()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self._api.create_todo(self._project_id, item.summary)
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        todo_id = int(item.uid)
        done = item.status == TodoItemStatus.COMPLETED if item.status else None
        text = item.summary or None
        await self._api.update_todo(todo_id, done=done, text=text)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._api.delete_todo(int(uid))
        await self.coordinator.async_request_refresh()
