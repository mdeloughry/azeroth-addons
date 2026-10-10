"""Logging helpers.

Decky injects a ``decky`` module with a ready-made logger. Outside Decky
(tests, local scripts) we fall back to a stdlib logger.

Two rules are enforced here:
1. Every operation logs a context line: installation / engine / provider / operation.
2. Credentials never reach the log, even if a caller passes them by accident.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Mapping

_LOGGER: logging.Logger | None = None

# Environment variables that must never be logged or echoed back to the frontend.
SENSITIVE_ENV_KEYS = frozenset(
    {
        "INSTAWOW_ACCESS_TOKENS_CFCORE",
        "INSTAWOW_ACCESS_TOKENS_GITHUB",
        "INSTAWOW_ACCESS_TOKENS_WAGO",
        "INSTAWOW_ACCESS_TOKENS_WOWI",
        "AZEROTH_CF_API_KEY",
        "AZEROTH_GITHUB_TOKEN",
        "AZEROTH_WAGO_TOKEN",
        "AZEROTH_WOWI_TOKEN",
    }
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(x-api-key|api[-_]?key|authorization|bearer|token)\s*[:=]\s*([^\s,;\"']{4,})"),
    re.compile(r"(?i)\b(INSTAWOW_ACCESS_TOKENS_[A-Z]+|AZEROTH_[A-Z_]*TOKEN|AZEROTH_CF_API_KEY)\s*=\s*\S+"),
)


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = _build_logger()
    return _LOGGER


def _build_logger() -> logging.Logger:
    try:  # pragma: no cover - only available inside Decky Loader
        import decky  # type: ignore

        logger = getattr(decky, "logger", None)
        if logger is not None:
            return logger
    except Exception:  # noqa: BLE001 - decky is optional
        pass

    logger = logging.getLogger("azeroth-addons")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("AZEROTH_LOG_LEVEL", "INFO").upper())
        logger.propagate = False
    return logger


def ctx(**fields: Any) -> str:
    """Render a stable log context: ``installation=… engine=… provider=… operation=…``."""
    order = ("installation", "engine", "provider", "operation")
    parts: list[str] = []
    for key in order:
        value = fields.pop(key, None)
        if value:
            parts.append(f"{key}={value}")
    for key in sorted(fields):
        value = fields[key]
        if value is None or value is False:
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)


def redact(text: str) -> str:
    """Strip credential-shaped substrings from arbitrary text."""
    redacted = text or ""
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: f"{m.group(1)}=<redacted>", redacted)
    return redacted


def safe_env(env: Mapping[str, str]) -> dict[str, str]:
    """A loggable copy of an environment mapping: sensitive values masked."""
    out: dict[str, str] = {}
    for key, value in env.items():
        if key in SENSITIVE_ENV_KEYS or key.endswith("_TOKEN") or key.endswith("_API_KEY"):
            out[key] = "<redacted>"
        else:
            out[key] = value
    return out


def mask_secret(value: str) -> str:
    """A display-safe hint for a stored credential. Never reversible."""
    if not value:
        return ""
    if len(value) <= 6:
        return "•" * len(value)
    return f"{value[:2]}{'•' * 6}{value[-2:]}"
