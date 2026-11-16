"""Todo platform for otodo integration."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OtodoAPI, OtodoError
from .coordinator import OtodoConfigEntry, OtodoCoordinator

PARALLEL_UPDATES = 0  # all reads go through the coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OtodoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    coordinator = data.coordinator
    known: set[int] = set()

    @callback
    def _add_new_projects() -> None:
        """Add an entity for every project not seen yet, e.g. one created later."""
        new = [pid for pid in coordinator.data if pid not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            OtodoTodoList(coordinator, data.api, pid, entry.entry_id) for pid in new
        )

    _add_new_projects()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_projects))


class OtodoTodoList(CoordinatorEntity[OtodoCoordinator], TodoListEntity):
    """A single otodo project as a HA todo list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(
        self,
        coordinator: OtodoCoordinator,
        api: OtodoAPI,
        project_id: int,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._project_id = project_id
        self._attr_unique_id = f"{entry_id}_{project_id}"
        self._update_from_data()

    @property
    def available(self) -> bool:
        # A project deleted in otodo drops out of the data; show it as
        # unavailable rather than as an empty list.
        return super().available and self._project_id in self.coordinator.data

    def _update_from_data(self) -> None:
        project = self.coordinator.data.get(self._project_id)
        if project is None:
            return
        self._attr_name = project["name"]  # follows renames
        self._attr_todo_items = [
            TodoItem(
                uid=str(t["id"]),
                summary=t["text"],
                status=(
                    TodoItemStatus.COMPLETED if t["done"] else TodoItemStatus.NEEDS_ACTION
                ),
            )
            for t in project["todos"]
        ]

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()

    async def _call(self, action: Awaitable) -> None:
        """Run an API call and refresh, reporting failures to the user."""
        try:
            await action
        except OtodoError as err:
            raise HomeAssistantError(f"otodo: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self._call(self._api.create_todo(self._project_id, item.summary or ""))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        done = item.status == TodoItemStatus.COMPLETED if item.status else None
        await self._call(
            self._api.update_todo(int(item.uid), done=done, text=item.summary or None)
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        async def delete_all() -> None:
            for uid in uids:
                await self._api.delete_todo(int(uid))

        await self._call(delete_all())
