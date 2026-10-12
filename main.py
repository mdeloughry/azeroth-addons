"""Decky Loader entry point.

This module is deliberately thin: it resolves the plugin environment, builds the
:class:`~azeroth_addons.context.AzerothAddonsContext`, and exposes every
operation the frontend may call. All logic lives in the backend package so it
can be tested without Decky.

Backend methods are plain ``async def`` methods on ``class Plugin`` - the Decky
loader discovers them by name and dispatches index-based arguments. Each method
is wrapped by ``@rpc`` so callers always receive a structured envelope.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

_PLUGIN_DIR = os.environ.get("DECKY_PLUGIN_DIR") or os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_PLUGIN_DIR, "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from azeroth_addons import events as az_events  # noqa: E402
from azeroth_addons.context import AzerothAddonsContext, PluginEnvironment  # noqa: E402
from azeroth_addons.errors import INVALID_ARGUMENT, AzerothAddonsError, rpc  # noqa: E402
from azeroth_addons.logctx import get_logger  # noqa: E402

logger = get_logger()

try:  # pragma: no cover - only present inside Decky Loader
    import decky  # type: ignore
except Exception:  # noqa: BLE001 - the backend is importable without Decky
    decky = None  # type: ignore[assignment]


class Plugin:
    def __init__(self) -> None:
        self._context: AzerothAddonsContext | None = None
        self._warmup: asyncio.Task[Any] | None = None

    # -- internals ----------------------------------------------------------

    async def _emit(self, event: str, payload: Any = None) -> None:
        if decky is None:
            return
        try:
            await decky.emit(event, payload)
        except Exception as exc:  # noqa: BLE001 - never let a UI event break an operation
            logger.debug("emit %s failed: %s", event, exc)

    def _ctx(self) -> AzerothAddonsContext:
        if self._context is None:
            environment = PluginEnvironment.from_environment()
            self._context = AzerothAddonsContext(environment, emit=self._emit).initialize()
        self._context.require_initialized()
        return self._context

    # -- lifecycle ----------------------------------------------------------

    async def _main(self) -> None:
        context = self._ctx()
        logger.info(
            "Azeroth Addons %s starting (plugin_dir=%s)",
            context.runtime_status()["pluginVersion"],
            context.env.plugin_dir,
        )
        await context.announce_runtime_status()
        # Warm the bundled engine without blocking startup; the UI shows the
        # state through runtime-status events.
        self._warmup = context.start_engine_prepare()

    async def _unload(self) -> None:
        if self._context is not None:
            self._context.cancel_tasks()
            self._context.shutdown()
        logger.info("Azeroth Addons stopped")

    async def _uninstall(self) -> None:
        logger.info("Azeroth Addons uninstalled")

    async def _migration(self) -> None:
        if decky is None:
            return
        try:  # pragma: no cover - depends on a legacy on-disk layout
            decky.migrate_logs(os.path.join(decky.DECKY_USER_HOME, ".config", "azeroth-addons.log"))
            decky.migrate_settings(os.path.join(decky.DECKY_HOME, "settings", "azeroth-addons.json"))
            decky.migrate_runtime(os.path.join(decky.HOME, "azeroth-addons"))
        except Exception as exc:  # noqa: BLE001 - migration is best effort
            logger.debug("migration skipped: %s", exc)

    # -- runtime / engines / providers --------------------------------------

    @rpc
    async def get_runtime_status(self) -> dict[str, Any]:
        return self._ctx().runtime_status()

    @rpc
    async def prepare_engine(self) -> dict[str, Any]:
        return await self._ctx().prepare_engine()

    @rpc
    async def get_engines(self) -> dict[str, Any]:
        context = self._ctx()
        return {
            "default": context.engines.default_id,
            "engines": await context.service.engine_statuses(),
        }

    @rpc
    async def get_engine_status(self, engine_id: str | None = None) -> dict[str, Any]:
        engine = self._ctx().engines.get(engine_id)
        return (await engine.status()).to_dict()

    @rpc
    async def get_providers(self) -> dict[str, Any]:
        context = self._ctx()
        return {
            "providers": await context.service.provider_statuses(),
            "enabled": [provider.provider_id for provider in context.providers.enabled()],
        }

    @rpc
    async def get_provider_status(self, provider_id: str | None = None) -> dict[str, Any]:
        context = self._ctx()
        if provider_id:
            provider = context.providers.get(provider_id)
            return (await provider.health()).to_dict()
        return {"providers": await context.service.provider_statuses()}

    # -- installations ------------------------------------------------------

    @rpc
    async def get_installations(self) -> dict[str, Any]:
        context = self._ctx()
        return {
            "installations": context.service.installations_payload(),
            "selectedId": context.installations.selected_id(),
            "summary": context.installations.summary(),
            "running": sorted(context.service.running_ids()),
        }

    @rpc
    async def discover_wow_installations(self) -> dict[str, Any]:
        return await self._rescan()

    @rpc
    async def rescan_installations(self) -> dict[str, Any]:
        return await self._rescan()

    @rpc
    async def add_installation(self) -> dict[str, Any]:
        return await self._rescan()

    async def _rescan(self) -> dict[str, Any]:
        context = self._ctx()
        result = context.installations.rescan()
        context.service.invalidate()
        await context.service.installations_changed()
        payload = result.to_dict()
        payload["installations"] = context.service.installations_payload()
        payload["selectedId"] = context.installations.selected_id()
        return payload

    @rpc
    async def add_custom_installation(self, path: str) -> dict[str, Any]:
        context = self._ctx()
        result = context.installations.add_custom(path)
        context.service.invalidate()
        await context.service.installations_changed()
        result["installations"] = context.service.installations_payload()
        result["selectedId"] = context.installations.selected_id()
        return result

    @rpc
    async def validate_custom_path(self, path: str) -> dict[str, Any]:
        if not path or not str(path).strip():
            raise AzerothAddonsError(INVALID_ARGUMENT, "Choose a folder first.")
        return self._ctx().preview_path(str(path))

    @rpc
    async def get_installation_options(self) -> dict[str, Any]:
        return {"options": self._ctx().installation_options()}

    @rpc
    async def update_installation(self, installation_id: str, display_name: str) -> dict[str, Any]:
        context = self._ctx()
        context.installations.rename(installation_id, display_name)
        await context.service.installations_changed()
        return {
            "installations": context.service.installations_payload(),
            "selectedId": context.installations.selected_id(),
        }

    @rpc
    async def remove_installation(self, installation_id: str) -> dict[str, Any]:
        context = self._ctx()
        context.installations.remove(installation_id)
        context.service.invalidate(installation_id)
        await context.service.installations_changed()
        return {
            "installations": context.service.installations_payload(),
            "selectedId": context.installations.selected_id(),
        }

    @rpc
    async def set_selected_installation(self, installation_id: str | None) -> dict[str, Any]:
        context = self._ctx()
        context.installations.set_selected(installation_id)
        return {
            "selectedId": context.installations.selected_id(),
            "installations": context.service.installations_payload(),
        }

    @rpc
    async def get_engine_profile(self, installation_id: str) -> dict[str, Any]:
        context = self._ctx()
        installation = context.installations.get(installation_id)
        engine = context.engines.get()
        profile_status = getattr(engine, "profile_status", None)
        if profile_status is None:
            return {"installationId": installation.id, "engineProfile": installation.engine_profile}
        payload = await profile_status(installation)
        payload["installationId"] = installation.id
        payload["engineProfile"] = installation.engine_profile
        return payload

    # -- addons -------------------------------------------------------------

    @rpc
    async def get_installed_addons(self, installation_id: str, refresh: bool = False) -> dict[str, Any]:
        return await self._ctx().service.installed(installation_id, refresh=bool(refresh))

    @rpc
    async def reconcile_addons(self, installation_id: str) -> dict[str, Any]:
        return await self._ctx().service.reconcile(installation_id)

    @rpc
    async def check_updates(self, installation_id: str) -> dict[str, Any]:
        return await self._ctx().service.check_updates(installation_id)

    @rpc
    async def search_addons(self, installation_id: str, query: str, limit: int = 25, provider_ids: list[str] | None = None) -> dict[str, Any]:
        if provider_ids is not None and (not isinstance(provider_ids, list) or not all(isinstance(value, str) for value in provider_ids)):
            raise AzerothAddonsError(INVALID_ARGUMENT, "Select valid addon sources.")
        return await self._ctx().search.search(installation_id, query, limit=int(limit or 25), provider_ids=provider_ids)

    @rpc
    async def install_addon(
        self,
        installation_id: str,
        provider: str,
        provider_id: str,
        replace: bool = False,
    ) -> dict[str, Any]:
        addon = await self._ctx().service.install(
            installation_id, provider, provider_id, replace=bool(replace)
        )
        return {"installationId": installation_id, "addon": addon.to_dict()}

    @rpc
    async def update_addon(self, installation_id: str, addon_id: str) -> dict[str, Any]:
        addon = await self._ctx().service.update(installation_id, addon_id)
        return {"installationId": installation_id, "addon": addon.to_dict()}

    @rpc
    async def update_all(self, installation_id: str) -> dict[str, Any]:
        return await self._ctx().service.update_all(installation_id)

    @rpc
    async def remove_addon(self, installation_id: str, addon_id: str) -> dict[str, Any]:
        return await self._ctx().service.remove(installation_id, addon_id)

    @rpc
    async def rollback_addon(self, installation_id: str, addon_id: str) -> dict[str, Any]:
        addon = await self._ctx().service.rollback(installation_id, addon_id)
        return {"installationId": installation_id, "addon": addon.to_dict()}

    # -- diagnostics --------------------------------------------------------

    @rpc
    async def get_error_journal(self, limit: int = 50) -> dict[str, Any]:
        return self._ctx().journal_payload(int(limit or 50))

    @rpc
    async def clear_error_journal(self) -> dict[str, Any]:
        return self._ctx().clear_journal()

    @rpc
    async def report_frontend_error(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AzerothAddonsError(INVALID_ARGUMENT, "An error report must be an object.")
        event = self._ctx().record_frontend_error(payload)
        return {"recorded": True, "eventId": event.get("id")}

    @rpc
    async def get_error_reporting(self) -> dict[str, Any]:
        return self._ctx().reporting_payload()

    @rpc
    async def send_test_error_report(self) -> dict[str, Any]:
        return await self._ctx().send_test_report()

    # -- settings -----------------------------------------------------------

    @rpc
    async def get_settings(self) -> dict[str, Any]:
        return self._ctx().settings_payload()

    @rpc
    async def set_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise AzerothAddonsError(INVALID_ARGUMENT, "Settings must be given as a set of values.")
        return self._ctx().update_settings(values)

    @rpc
    async def set_credential(self, provider: str, value: str | None) -> dict[str, Any]:
        return self._ctx().set_credential(str(provider), value)

    @rpc
    async def clear_credential(self, provider: str) -> dict[str, Any]:
        return self._ctx().set_credential(str(provider), None)


def _event_names() -> list[str]:
    return list(az_events.ALL_EVENTS)
