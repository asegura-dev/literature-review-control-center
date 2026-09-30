"""The one HTTP client of ADR-0011: what it refuses before sending, and how it waits and retries.

``respx`` replaces the transport, so nothing leaves the machine. A request to a route that was
not mocked raises, which is how "nothing was sent" is asserted: no route is defined, and the
call count stays at zero.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from lrcc.adapters.http import ATTEMPTS, HttpClient
from lrcc.domain.config import HostConfig, NetworkConfig
from lrcc.domain.errors import NetworkError

URL = "https://example.org/api"
ALLOWED = NetworkConfig(enabled=True, hosts={"example.org": HostConfig(min_interval=2.0)})


class Waits:
    """A fake clock and sleep: records the waits asked for, and never really waits."""

    def __init__(self) -> None:
        """Start the clock at zero."""
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        """Return the fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Record the wait and advance the fake time by it."""
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def waits() -> Waits:
    """A fresh fake clock."""
    return Waits()


def _client(network: NetworkConfig, waits: Waits) -> HttpClient:
    return HttpClient(network, sleep=waits.sleep, clock=waits.clock)


def test_a_request_to_an_allowed_host(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """The body comes back, the parameters go out, and the client names itself."""
    route = respx_mock.get(URL, params={"q": "a b"}).mock(
        return_value=httpx.Response(200, content=b"answer")
    )
    assert _client(ALLOWED, waits).get(URL, {"q": "a b"}) == b"answer"
    assert route.calls.last.request.headers["User-Agent"].startswith("lrcc/")


@pytest.mark.parametrize(
    ("network", "url", "expected"),
    [
        (NetworkConfig(), URL, "the network is off"),
        (NetworkConfig(enabled=False, hosts=ALLOWED.hosts), URL, "the network is off"),
        (ALLOWED, "https://elsewhere.example/api", "elsewhere.example is not an allowed host"),
        (ALLOWED, "https://example.org.evil.test/api", "is not an allowed host"),
        (ALLOWED, "http://example.org/api", "is not a plain HTTPS address"),
        (ALLOWED, "https://example.org:8443/api", "is not a plain HTTPS address"),
    ],
)
def test_refusals_happen_before_anything_is_sent(
    respx_mock: respx.MockRouter, waits: Waits, network: NetworkConfig, url: str, expected: str
) -> None:
    """Off, unlisted, or not HTTPS: the request is refused and no request is made."""
    with pytest.raises(NetworkError, match=expected):
        _client(network, waits).get(url, {})
    assert respx_mock.calls.call_count == 0


def test_a_redirect_is_not_followed(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """A redirect could lead outside the allowlist, so it is an error, not a second request."""
    respx_mock.get(URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://elsewhere.example/"})
    )
    with pytest.raises(NetworkError, match="answered HTTP 302"):
        _client(ALLOWED, waits).get(URL, {})
    assert respx_mock.calls.call_count == 1


def test_a_busy_host_is_retried_with_backoff(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """HTTP 503 and 429 are tried again, waiting longer each time."""
    respx_mock.get(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(429),
            httpx.Response(200, content=b"answer"),
        ]
    )
    assert _client(ALLOWED, waits).get(URL, {}) == b"answer"
    assert respx_mock.calls.call_count == 3
    assert len(waits.slept) >= 2


def test_a_transport_error_is_retried(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """A dropped connection is worth another attempt."""
    respx_mock.get(URL).mock(
        side_effect=[httpx.ConnectError("dropped"), httpx.Response(200, content=b"answer")]
    )
    assert _client(ALLOWED, waits).get(URL, {}) == b"answer"


def test_it_gives_up_after_the_last_attempt(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """A host that never answers is reported, with the last failure as the detail."""
    respx_mock.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(NetworkError, match=f"did not answer after {ATTEMPTS} attempts") as caught:
        _client(ALLOWED, waits).get(URL, {})
    assert respx_mock.calls.call_count == ATTEMPTS
    assert caught.value.details == ("HTTP 503",)


def test_a_client_error_is_not_retried(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """HTTP 404 will not change by asking again."""
    respx_mock.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(NetworkError, match="answered HTTP 404"):
        _client(ALLOWED, waits).get(URL, {})
    assert respx_mock.calls.call_count == 1


def test_requests_to_one_host_are_spaced(respx_mock: respx.MockRouter, waits: Waits) -> None:
    """The second request waits out the host's ``min_interval``; the first does not wait."""
    respx_mock.get(URL).mock(return_value=httpx.Response(200, content=b"answer"))
    client = _client(ALLOWED, waits)
    client.get(URL, {})
    assert waits.slept == []
    waits.now += 0.5
    client.get(URL, {})
    assert waits.slept == [1.5]
