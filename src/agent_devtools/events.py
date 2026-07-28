from collections.abc import Awaitable
from typing import Protocol


class ActionEventCollector(Protocol):
    def start(self) -> object | Awaitable[object]: ...

    def finish(
        self,
    ) -> list[dict[str, object]] | Awaitable[list[dict[str, object]]]: ...
