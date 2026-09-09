from __future__ import annotations

from abc import ABC, abstractmethod

from cdh.verification.aggregation import GateResult


class Gate(ABC):
    name: str = ""
    enabled: bool = True

    @abstractmethod
    def should_run(self, file_path: str) -> bool:
        ...

    @abstractmethod
    async def run(self, project_dir: str) -> GateResult:
        ...