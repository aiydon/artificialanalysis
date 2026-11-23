from __future__ import annotations

import logging
import random
import time
from urllib.parse import urljoin

import httpx

from .config import BASE_URL

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_BACKOFF = 10.0


class FetchError(RuntimeError):
    pass


class Fetcher:
    def __init__(self, proxy: str | None, timeout: float, retries: int) -> None:
        self.retries = retries
        self._client = httpx.Client(
            proxy=proxy,
            timeout=timeout,
            follow_redirects=True,
            headers=HEADERS,
            # An explicit proxy wins; otherwise honour HTTP(S)_PROXY from the environment.
            trust_env=proxy is None,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, path: str) -> str:
        url = urljoin(BASE_URL, path)
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                response = self._client.get(url)
                if response.status_code in RETRY_STATUS and attempt < self.retries:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type:
                    raise FetchError(f"{url}: unexpected content-type {content_type!r}")
                return response.text
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code not in RETRY_STATUS:
                    break
            except httpx.TransportError as exc:
                last_error = exc

            if attempt < self.retries:
                delay = min(2.0**attempt, MAX_BACKOFF) + random.uniform(0, 1)
                log.warning("fetch %s failed (%s); retry in %.1fs", url, last_error, delay)
                time.sleep(delay)

        raise FetchError(f"{url}: {last_error}") from last_error
