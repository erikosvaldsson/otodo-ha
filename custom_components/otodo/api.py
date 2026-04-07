"""API client for otodo."""

from __future__ import annotations

import aiohttp


class OtodoAPI:
    """Async client for the otodo REST API."""

    def __init__(self, url: str, api_key: str, session: aiohttp.ClientSession) -> None:
        self._url = url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._session = session

    async def list_projects(self) -> list[dict]:
        async with self._session.get(
            f"{self._url}/api/projects", headers=self._headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def list_todos(self, project_id: int) -> list[dict]:
        async with self._session.get(
            f"{self._url}/api/projects/{project_id}/todos", headers=self._headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def create_todo(self, project_id: int, text: str) -> dict:
        async with self._session.post(
            f"{self._url}/api/projects/{project_id}/todos",
            headers=self._headers,
            json={"text": text},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def update_todo(
        self,
        todo_id: int,
        *,
        done: bool | None = None,
        text: str | None = None,
    ) -> dict:
        payload: dict = {}
        if done is not None:
            payload["done"] = done
        if text is not None:
            payload["text"] = text
        async with self._session.patch(
            f"{self._url}/api/todos/{todo_id}",
            headers=self._headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def delete_todo(self, todo_id: int) -> None:
        async with self._session.delete(
            f"{self._url}/api/todos/{todo_id}", headers=self._headers
        ) as resp:
            resp.raise_for_status()

    async def validate(self) -> bool:
        """Return True if the connection and API key are valid."""
        try:
            await self.list_projects()
            return True
        except (aiohttp.ClientError, KeyError):
            return False
