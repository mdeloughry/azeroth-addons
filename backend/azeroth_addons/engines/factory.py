"""Engine wiring.

The engine registry is built here so the rest of the application never has to
know which engine class is in use.
"""

from __future__ import annotations

from .. import BUNDLED_INSTAWOW_VERSION
from ..logctx import get_logger
from ..settings import SettingsStore
from .base import EngineStatus
from .instawow import InstawowAdapter, InstawowEngine
from .registry import EngineRegistry

logger = get_logger()


def build_registry(
    target: EngineRegistry,
    *,
    binary_path: str,
    home_dir: str,
    settings: SettingsStore,
    status_callback=None,
    bundled_version: str = BUNDLED_INSTAWOW_VERSION,
) -> EngineRegistry:
    """Register every engine into ``target``.

    ``target`` is required on purpose: a shared module-level registry would let
    two application contexts silently diverge.
    """
    adapter = InstawowAdapter(
        binary_path,
        home_dir,
        token_provider=settings.credentials,
    )
    engine = InstawowEngine(
        adapter,
        settings=settings,
        bundled_version=bundled_version,
        status_callback=status_callback,
    )
    target.register(engine, default=True)
    return target
