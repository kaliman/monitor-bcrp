"""HTTP client for source downloads."""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request

from .config import SourceSettings

log = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when a remote resource cannot be downloaded."""


class HttpClient:
    def __init__(
        self,
        source: SourceSettings,
        timeout: int,
        retries: int,
        backoff_seconds: float,
    ) -> None:
        self._source = source
        self._timeout = timeout
        self._retries = max(1, retries)
        self._backoff = max(0.0, backoff_seconds)

    def get(self, url: str, timeout: int | None = None) -> bytes:
        headers = {
            "User-Agent": self._source.user_agent,
            "Accept-Language": self._source.accept_language,
            "Accept": "*/*",
        }
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(
                    request, timeout=timeout or self._timeout
                ) as response:
                    return response.read()
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
            ) as exc:
                last_error = exc
                code = getattr(exc, "code", None)
                log.warning(
                    "HTTP attempt %d/%d failed (%s)",
                    attempt,
                    self._retries,
                    code or type(exc).__name__,
                )
                if attempt < self._retries:
                    time.sleep(self._backoff * (2 ** (attempt - 1)))
        raise FetchError(
            f"request failed after {self._retries} attempts"
        ) from last_error
