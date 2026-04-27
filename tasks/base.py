from __future__ import annotations

from abc import ABC, abstractmethod

from models import ExecutionResult


class TaskExecutor(ABC):
    @abstractmethod
    def execute(self, config: dict) -> ExecutionResult: ...
