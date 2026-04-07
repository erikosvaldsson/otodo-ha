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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OtodoAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    api: OtodoAPI = entry.runtime_data
    projects = await api.list_projects()
    async_add_entities(
        [OtodoTodoList(api, project, entry.entry_id) for project in projects],
        update_before_add=True,
    )


class OtodoTodoList(TodoListEntity):
    """A single otodo project as a HA todo list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, api: OtodoAPI, project: dict, entry_id: str) -> None:
        self._api = api
        self._project_id: int = project["id"]
        self._attr_name = project["name"]
        self._attr_unique_id = f"{entry_id}_{self._project_id}"

    async def async_update(self) -> None:
        try:
            todos = await self._api.list_todos(self._project_id)
        except Exception:
            _LOGGER.exception("Failed to fetch todos for project %s", self._project_id)
            return
        self._attr_todo_items = [
            TodoItem(
                uid=str(t["id"]),
                summary=t["text"],
                status=(
                    TodoItemStatus.COMPLETED if t["done"] else TodoItemStatus.NEEDS_ACTION
                ),
            )
            for t in (todos or [])
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self._api.create_todo(self._project_id, item.summary)
        await self.async_update()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        todo_id = int(item.uid)
        done = item.status == TodoItemStatus.COMPLETED if item.status else None
        text = item.summary or None
        await self._api.update_todo(todo_id, done=done, text=text)
        await self.async_update()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._api.delete_todo(int(uid))
        await self.async_update()
