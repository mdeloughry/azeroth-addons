"""Minimal async HTTP built on the standard library.

The backend is stdlib-only by design: Decky cannot install Python packages into
a plugin, so providers use ``urllib`` executed in a worker thread.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .. import __version__
from ..errors import (
    ADDON_NOT_FOUND,
    DOWNLOAD_FAILED,
    NETWORK_ERROR,
    PROVIDER_AUTH_FAILED,
    PROVIDER_BAD_RESPONSE,
    PROVIDER_RATE_LIMITED,
    PROVIDER_UNAVAILABLE,
    AzerothAddonsError,
)

DEFAULT_TIMEOUT = 15.0
DOWNLOAD_TIMEOUT = 120.0
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

USER_AGENT = f"AzerothAddons/{__version__} (Decky Loader plugin)"


def build_url(url: str, params: Mapping[str, Any] | None = None) -> str:
    if not params:
        return url
    clean = {key: value for key, value in params.items() if value is not None}
    if not clean:
        return url
    separator = "&" if urllib.parse.urlparse(url).query else "?"
    return f"{url}{separator}{urllib.parse.urlencode(clean)}"


def _perform(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
    method: str = "GET",
    body: bytes | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - provider URLs are configured constants
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise AzerothAddonsError(
                DOWNLOAD_FAILED,
                "The remote file is larger than the safety limit.",
                details=f"url={url} limit={max_bytes}",
            )
        return response.status, dict(response.headers.items()), payload


def _map_http_error(error: urllib.error.HTTPError, url: str, provider: str | None) -> AzerothAddonsError:
    status = error.code
    remaining = error.headers.get("x-ratelimit-remaining") if error.headers else None
    retry_after = error.headers.get("retry-after") if error.headers else None
    detail = f"status={status} url={url}"
    if retry_after:
        detail += f" retry_after={retry_after}"
    if remaining is not None:
        detail += f" ratelimit_remaining={remaining}"

    if status in (401, 403):
        if remaining == "0" or status == 429:
            return AzerothAddonsError(
                PROVIDER_RATE_LIMITED,
                "The provider is rate limiting us. Try again later.",
                details=detail,
                provider=provider,
            )
        return AzerothAddonsError(
            PROVIDER_AUTH_FAILED,
            "The provider rejected our credentials.",
            details=detail,
            provider=provider,
        )
    if status == 404:
        return AzerothAddonsError(
            ADDON_NOT_FOUND,
            "That addon was not found on the provider.",
            details=detail,
            provider=provider,
        )
    if status == 429:
        return AzerothAddonsError(
            PROVIDER_RATE_LIMITED,
            "The provider is rate limiting us. Try again later.",
            details=detail,
            provider=provider,
        )
    if status >= 500:
        return AzerothAddonsError(
            PROVIDER_UNAVAILABLE,
            "The provider is having problems right now.",
            details=detail,
            provider=provider,
        )
    return AzerothAddonsError(
        PROVIDER_UNAVAILABLE,
        "The provider rejected the request.",
        details=detail,
        provider=provider,
    )


async def fetch_json(
    url: str,
    *,
    provider: str | None = None,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    method: str = "GET",
    body: bytes | None = None,
    allow_missing: bool = False,
) -> Any:
    """GET (or POST) a JSON document, mapping transport failures to structured errors."""
    final_url = build_url(url, params)
    try:
        status, _, payload = await asyncio.to_thread(
            _perform,
            final_url,
            headers=headers or {},
            timeout=timeout,
            method=method,
            body=body,
        )
    except urllib.error.HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise _map_http_error(error, final_url, provider) from error
    except urllib.error.URLError as error:
        raise AzerothAddonsError(
            NETWORK_ERROR,
            "Could not reach the provider. Check your connection.",
            details=f"url={final_url} error={error.reason}",
            provider=provider,
        ) from error
    except TimeoutError as error:
        raise AzerothAddonsError(
            NETWORK_ERROR,
            "The provider took too long to respond.",
            details=f"url={final_url}",
            provider=provider,
        ) from error

    if status == 204 or not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AzerothAddonsError(
            PROVIDER_BAD_RESPONSE,
            "The provider returned an unexpected response.",
            details=f"url={final_url}",
            provider=provider,
        ) from error


def describe_rate_limit(headers: Mapping[str, str]) -> dict[str, str]:
    keys = ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after")
    return {key: str(headers[key]) for key in keys if key in headers}
