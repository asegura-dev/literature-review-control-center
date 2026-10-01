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
from dataclasses import dataclass
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

    def fetch(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        secret_params: Mapping[str, str] | None = None,
        secret_headers: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> RawResponse:
        """Fetch ``url`` and return the answer with the address that was asked.

        The recorded address holds the ordinary parameters. A secret parameter is recorded by
        name with the value ``[redacted]``, and headers are not recorded at all (ADR-0015).

        Args:
            url: An HTTPS URL on an allowed host.
            params: The query parameters, recorded as sent.
            secret_params: Query parameters holding keys: sent, never recorded.
            secret_headers: Headers holding keys: sent, never recorded.
            headers: Other headers to send.

        Returns:
            The body exactly as received, and the address with every key redacted.

        Raises:
            NetworkError: As :meth:`get`.
        """
        body = self.get(
            url, params, secret_params=secret_params, secret_headers=secret_headers, headers=headers
        )
        redacted = {name: "[redacted]" for name in (secret_params or {})}
        recorded = urlencode({**params, **redacted}, safe="[]")
        return RawResponse(url=f"{url}?{recorded}", body=body)

    def get(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        secret_params: Mapping[str, str] | None = None,
        secret_headers: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes:
        """Fetch ``url`` and return the body of the answer.

        Args:
            url: An HTTPS URL on an allowed host.
            params: The query parameters.
            secret_params: Query parameters holding keys.
            secret_headers: Headers holding keys.
            headers: Other headers to send.

        Returns:
            The response body.

        Raises:
            NetworkError: If the request is refused, the host answers with an error or with an
                answer that repeats a key, or it does not answer after every attempt. No message
                ever contains a key.
        """
        host = self._allowed_host(url)
        secrets = tuple(
            value
            for value in (*(secret_params or {}).values(), *(secret_headers or {}).values())
            if value
        )
        request = _Request(
            url=url,
            params={**params, **(secret_params or {})},
            headers={**(headers or {}), **(secret_headers or {})},
            secrets=secrets,
        )
        retrying = Retrying(
            stop=stop_after_attempt(ATTEMPTS),
            wait=wait_exponential(multiplier=1, max=30),
            retry=retry_if_exception_type(_Retryable),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            return retrying(self._get_once, host, request)
        except _Retryable as problem:
            raise NetworkError(
                f"{host} did not answer after {ATTEMPTS} attempts",
                [_scrub(str(problem), secrets)],
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

    def _get_once(self, host: str, request: _Request) -> bytes:
        self._wait_for_turn(host)
        try:
            response = self._client.get(
                request.url, params=dict(request.params), headers=dict(request.headers)
            )
        except httpx.TransportError as problem:
            raise _Retryable(f"{type(problem).__name__}: {problem}") from None
        status = response.status_code
        if status == 429 or status >= 500:
            raise _Retryable(f"HTTP {status}")
        if status != 200:
            # A refusal is not retried: for a service with a daily quota, a retry spends calls.
            snippet = _snippet(response.content, request.secrets)
            raise NetworkError(
                f"{host} answered HTTP {status}, so nothing was read", [snippet] if snippet else []
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise NetworkError(f"{host} answered with more than {MAX_RESPONSE_BYTES} bytes")
        if any(secret.encode() in response.content for secret in request.secrets):
            raise NetworkError(
                f"{host} answered with a key this request sent, so the answer was not kept",
                ["a stored answer is kept byte for byte, and must never hold a key (ADR-0015)"],
            )
        return response.content


@dataclass(frozen=True, repr=False)
class _Request:
    """What one request sends, and the values in it that must never be shown."""

    url: str
    params: Mapping[str, str]
    headers: Mapping[str, str]
    secrets: tuple[str, ...]


def _scrub(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        text = text.replace(secret, "[redacted]")
    return text


def _snippet(body: bytes, secrets: tuple[str, ...]) -> str:
    """Quote the start of an error answer, as one line, with any key replaced."""
    text = " ".join(body[:600].decode("utf-8", errors="replace").split())
    return _scrub(text, secrets)[:300]
