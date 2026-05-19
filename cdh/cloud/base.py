from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class CloudProvider(ABC):
    name: str = ""

    @abstractmethod
    async def deploy(self, project_path: str, version: Optional[str] = None) -> str:
        ...

    @abstractmethod
    async def status(self) -> str:
        ...

    @abstractmethod
    async def rollback(self, version: str) -> str:
        ...
