"""The one HTTP client of the program (ADR-0011).

Every request LRCC makes goes through :class:`HttpClient`, so there is one allowlist to defend.
It refuses, before anything is sent, a request while the network is off, to a host the
configuration does not name, or over anything but HTTPS. It never follows a redirect, which
could lead to a host outside the list. ``tests/test_egress.py`` fails if any other module imports
an HTTP library.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from importlib.metadata import version
from urllib.parse import urlencode, urlsplit

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from lrcc.domain.config import NetworkConfig
from lrcc.domain.errors import NetworkError
from lrcc.domain.record import RawResponse

#: How many times a request is tried before giving up.
ATTEMPTS = 4
#: A response larger than this is refused: content from outside gets a ceiling.
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 30.0


class _Retryable(Exception):
    """A failure worth another attempt: a transport error, HTTP 429 or HTTP 5xx."""


class HttpClient:
    """GET requests to allowed hosts only, rate-limited per host and retried with backoff."""

    def __init__(
        self,
        network: NetworkConfig,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create the client.

        Args:
            network: Whether requests are allowed, and the hosts that may be contacted.
            sleep: Waits the given seconds. Replaced in tests, so they never really wait.
            clock: Returns a monotonic time in seconds. Replaced in tests.
        """
        self._network = network
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._client = httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": f"lrcc/{version('literature-review-control-center')}"},
        )

    def fetch(self, url: str, params: Mapping[str, str]) -> RawResponse:
        """Fetch ``url`` and return the answer with the address that was asked.

        Args:
            url: An HTTPS URL on an allowed host.
            params: The query parameters.

        Returns:
            The body exactly as received, and the full address, so a run can store both.

        Raises:
            NetworkError: As :meth:`get`.
        """
        return RawResponse(url=f"{url}?{urlencode(params)}", body=self.get(url, params))

    def get(self, url: str, params: Mapping[str, str]) -> bytes:
        """Fetch ``url`` and return the body of the answer.

        Args:
            url: An HTTPS URL on an allowed host.
            params: The query parameters.

        Returns:
            The response body.

        Raises:
            NetworkError: If the request is refused, the host answers with an error, or it does
                not answer after every attempt.
        """
        host = self._allowed_host(url)
        retrying = Retrying(
            stop=stop_after_attempt(ATTEMPTS),
            wait=wait_exponential(multiplier=1, max=30),
            retry=retry_if_exception_type(_Retryable),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            return retrying(self._get_once, host, url, params)
        except _Retryable as problem:
            raise NetworkError(
                f"{host} did not answer after {ATTEMPTS} attempts", [str(problem)]
            ) from None

    def _allowed_host(self, url: str) -> str:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if not self._network.enabled:
            raise NetworkError(
                "the network is off, so nothing was requested",
                ["set network.enabled to true in the configuration to allow requests"],
            )
        if parts.scheme != "https" or parts.port not in (None, 443):
            raise NetworkError(f"{url} is not a plain HTTPS address, so nothing was requested")
        if host not in self._network.hosts:
            raise NetworkError(
                f"{host} is not an allowed host, so nothing was requested",
                ["only hosts named under network.hosts in the configuration are contacted"],
            )
        return host

    def _wait_for_turn(self, host: str) -> None:
        interval = self._network.hosts[host].min_interval
        last = self._last_request.get(host)
        if last is not None:
            remaining = interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _get_once(self, host: str, url: str, params: Mapping[str, str]) -> bytes:
        self._wait_for_turn(host)
        try:
            response = self._client.get(url, params=dict(params))
        except httpx.TransportError as problem:
            raise _Retryable(f"{type(problem).__name__}: {problem}") from None
        status = response.status_code
        if status == 429 or status >= 500:
            raise _Retryable(f"HTTP {status}")
        if status != 200:
            raise NetworkError(f"{host} answered HTTP {status}, so nothing was read")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise NetworkError(f"{host} answered with more than {MAX_RESPONSE_BYTES} bytes")
        return response.content
