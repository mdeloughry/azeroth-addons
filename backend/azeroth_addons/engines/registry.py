"""Engine registry.

Adding an engine must never require frontend changes: register it here and the
RPC surface, status payloads and capability checks pick it up automatically.
"""

from __future__ import annotations

from typing import Iterator

from ..errors import ENGINE_UNAVAILABLE, AzerothAddonsError
from ..logctx import get_logger
from .base import AddonEngine, EngineStatus

logger = get_logger()


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, AddonEngine] = {}
        self._default_id: str | None = None

    def register(self, engine: AddonEngine, *, default: bool = False) -> None:
        self._engines[engine.engine_id] = engine
        if default or self._default_id is None:
            self._default_id = engine.engine_id
        logger.info("registered engine %s (default=%s)", engine.engine_id, self._default_id)

    def get(self, engine_id: str | None = None) -> AddonEngine:
        key = engine_id or self._default_id
        if not key or key not in self._engines:
            raise AzerothAddonsError(
                ENGINE_UNAVAILABLE,
                "The addon engine is not available.",
                details=f"requested={engine_id} known={sorted(self._engines)}",
                engine=engine_id or self._default_id,
            )
        return self._engines[key]

    def get_or_none(self, engine_id: str | None = None) -> AddonEngine | None:
        try:
            return self.get(engine_id)
        except AzerothAddonsError:
            return None

    @property
    def default_id(self) -> str | None:
        return self._default_id

    def ids(self) -> list[str]:
        return sorted(self._engines)

    def __iter__(self) -> Iterator[AddonEngine]:
        return iter(self._engines.values())

    async def statuses(self) -> list[EngineStatus]:
        statuses: list[EngineStatus] = []
        for engine in self._engines.values():
            try:
                statuses.append(await engine.status())
            except Exception as exc:  # noqa: BLE001 - one engine must not break the list
                logger.error("engine %s status failed: %s", engine.engine_id, exc)
                statuses.append(
                    EngineStatus(
                        engine_id=engine.engine_id,
                        display_name=engine.display_name,
                        state="error",
                        message="The engine reported an error.",
                        detail=str(exc),
                        capabilities=engine.capabilities(),
                    )
                )
        return statuses
