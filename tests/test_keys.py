"""API keys (ADR-0015): read from the ``.env`` beside the configuration, and never shown or kept.

Every key in these tests is fake. The real ``.env`` is never read: keys are looked for only
beside the configuration file, and every test's configuration lives in a temporary folder.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from lrcc.adapters.http import HttpClient
from lrcc.domain.config import HostConfig, NetworkConfig
from lrcc.domain.errors import ConfigError, NetworkError
from lrcc.domain.secrets import NO_SECRETS, load_secrets, parse_dotenv

KEY = "fake-key-3f9a2c7d1e5b"
URL = "https://example.org/api"
ALLOWED = NetworkConfig(enabled=True, hosts={"example.org": HostConfig(min_interval=0)})


def test_the_dotenv_format() -> None:
    """Comments, blanks, ``export`` and quotes, as LACC reads them; a malformed line is skipped."""
    text = (
        "# a comment\n"
        "\n"
        "IEEE_API_KEY=abc\n"
        "export SCOPUS_API_KEY = def \n"
        'NCBI_API_KEY="quoted value"\n'
        "SCOPUS_INSTTOKEN='single'\n"
        "this line has no equals sign\n"
        "9STARTS_WITH_DIGIT=x\n"
    )
    assert parse_dotenv(text) == {
        "IEEE_API_KEY": "abc",
        "SCOPUS_API_KEY": "def",
        "NCBI_API_KEY": "quoted value",
        "SCOPUS_INSTTOKEN": "single",
    }


def test_only_known_keys_are_kept_and_the_environment_wins(tmp_path: Path) -> None:
    """Unknown names are dropped, empty values are not keys, and the environment wins."""
    (tmp_path / ".env").write_text(
        "IEEE_API_KEY=from-file\nSCOPUS_API_KEY=\nOTHER_SECRET=dropped\n", encoding="utf-8"
    )
    secrets = load_secrets(tmp_path, {"IEEE_API_KEY": "from-environment"})
    assert secrets.values == {"IEEE_API_KEY": "from-environment"}
    assert secrets.get("SCOPUS_API_KEY") is None


def test_no_file_means_no_keys(tmp_path: Path) -> None:
    """A folder without ``.env`` is not an error: sources that need no key still work."""
    assert load_secrets(tmp_path, {}).values == {}


def test_a_missing_key_is_named_with_its_file_never_a_value(tmp_path: Path) -> None:
    """The message says which variable and which file, and shows no key at all."""
    (tmp_path / ".env").write_text(f"SCOPUS_API_KEY={KEY}\n", encoding="utf-8")
    secrets = load_secrets(tmp_path, {})
    with pytest.raises(ConfigError) as caught:
        secrets.require("IEEE_API_KEY", "IEEE Xplore")
    shown = caught.value.message + " ".join(caught.value.details)
    assert "IEEE Xplore needs IEEE_API_KEY" in shown
    assert str(tmp_path / ".env") in shown
    assert KEY not in shown


def test_the_printed_form_shows_names_not_values(tmp_path: Path) -> None:
    """A key object that ends up in a log or a traceback gives nothing away."""
    (tmp_path / ".env").write_text(f"IEEE_API_KEY={KEY}\n", encoding="utf-8")
    secrets = load_secrets(tmp_path, {})
    assert repr(secrets) == "Secrets(set: IEEE_API_KEY)"
    assert KEY not in repr(secrets) and KEY not in str(secrets)
    assert repr(NO_SECRETS) == "Secrets(set: none)"


def test_a_secret_parameter_is_sent_but_recorded_redacted(respx_mock: respx.MockRouter) -> None:
    """The source receives the key; the address a run keeps says only that a key was sent."""
    route = respx_mock.get(URL).mock(return_value=httpx.Response(200, content=b"answer"))
    response = HttpClient(ALLOWED).fetch(URL, {"q": "a"}, secret_params={"apikey": KEY})
    assert route.calls.last.request.url.params["apikey"] == KEY
    assert response.url == f"{URL}?q=a&apikey=[redacted]"
    assert KEY not in response.url


def test_a_secret_header_is_sent_and_never_recorded(respx_mock: respx.MockRouter) -> None:
    """Headers are not part of the recorded address at all."""
    route = respx_mock.get(URL).mock(return_value=httpx.Response(200, content=b"answer"))
    response = HttpClient(ALLOWED).fetch(URL, {"q": "a"}, secret_headers={"X-Key": KEY})
    assert route.calls.last.request.headers["X-Key"] == KEY
    assert response.url == f"{URL}?q=a"


def test_an_answer_that_repeats_a_key_is_refused(respx_mock: respx.MockRouter) -> None:
    """A stored answer is kept byte for byte, so one holding a key must not be kept at all."""
    respx_mock.get(URL).mock(return_value=httpx.Response(200, content=f"echo {KEY}".encode()))
    with pytest.raises(NetworkError, match="answered with a key") as caught:
        HttpClient(ALLOWED).fetch(URL, {}, secret_params={"apikey": KEY})
    assert KEY not in caught.value.message + " ".join(caught.value.details)


def test_an_error_answer_is_quoted_without_the_key(respx_mock: respx.MockRouter) -> None:
    """The start of a refusal is shown to explain it, with any key replaced."""
    respx_mock.get(URL).mock(
        return_value=httpx.Response(403, content=f"Developer Inactive for key {KEY}".encode())
    )
    with pytest.raises(NetworkError, match="answered HTTP 403") as caught:
        HttpClient(ALLOWED).get(URL, {}, secret_params={"apikey": KEY})
    assert caught.value.details == ("Developer Inactive for key [redacted]",)
    assert respx_mock.calls.call_count == 1
