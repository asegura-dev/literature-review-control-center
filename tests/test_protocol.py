"""The protocol, format 1: every field required, every problem named, the digest over bytes."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from lrcc.domain.errors import ProtocolError
from lrcc.domain.protocol import parse_protocol, protocol_digest

VALID: dict[str, Any] = {
    "format": 1,
    "review_id": "example",
    "title": "A synthetic review",
    "question": {
        "text": "What is known?",
        "framework": "PCC",
        "elements": {"population": "P", "concept": "C", "context": "C"},
    },
    "criteria": [
        {"code": "INC1", "text": "Included when..."},
        {"code": "EXC1", "text": "Excluded when..."},
    ],
    "sources": {"pubmed": {"query": "a AND b"}, "arxiv": {"query": "abs:a"}},
    "extraction": [{"name": "design", "description": "The study design."}],
}


def _encode(data: dict[str, Any]) -> bytes:
    return yaml.safe_dump(data, sort_keys=False).encode("utf-8")


def _details(data: bytes) -> tuple[str, ...]:
    with pytest.raises(ProtocolError) as caught:
        parse_protocol(data, source="protocol.yaml")
    assert caught.value.message == "protocol.yaml is not a valid protocol"
    return caught.value.details


def test_a_valid_protocol() -> None:
    """A complete protocol parses, and its codes are split by kind."""
    protocol = parse_protocol(_encode(VALID), source="protocol.yaml")
    assert protocol.review_id == "example"
    assert protocol.inclusion == ("INC1",)
    assert protocol.exclusion == ("EXC1",)
    assert set(protocol.sources) == {"pubmed", "arxiv"}


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(data: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = data
        for part in parents:
            target = target[int(part)] if part.isdigit() else target[part]
        if value is _DELETE:
            del target[last]
        elif last.isdigit():
            target[int(last)] = value
        else:
            target[last] = value

    return change


_DELETE = object()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (_set("title", ""), "title: must not be empty"),
        (_set("title", None), "title: must not be empty"),
        (_set("title", _DELETE), "title: is required"),
        (_set("format", 2), "format: must be 1"),
        (_set("review_id", "Bad_Id"), "review_id: must be 1 to 40 lowercase letters"),
        (_set("notes", "x"), "notes: is not a known field"),
        (_set("question.elements", {}), "question.elements: must have at least one entry"),
        (_set("criteria", []), "criteria: must have at least one entry"),
        (_set("criteria.0.code", "INC"), "criteria.0.code: must look like INC1 or EXC1"),
        (_set("criteria.0.code", "inc1"), "criteria.0.code: must look like INC1 or EXC1"),
        (_set("criteria.1.code", "INC1"), "criteria: codes must be unique; repeated: INC1"),
        (_set("criteria.1.code", "INC2"), "criteria: needs at least one exclusion criterion"),
        (_set("criteria.0.code", "EXC2"), "criteria: needs at least one inclusion criterion"),
        (_set("sources", {}), "sources: must have at least one entry"),
        (_set("sources.pubmd", {"query": "x"}), "sources: unknown source pubmd"),
        (_set("sources.pubmed.query", "  "), "sources.pubmed.query: must not be empty"),
        (_set("extraction.0.name", "Bad Name"), "extraction.0.name: must be lowercase"),
        (
            _set("extraction", [{"name": "a", "description": "x"}] * 2),
            "extraction: names must be unique; repeated: a",
        ),
    ],
)
def test_each_problem_is_named(change: Callable[[dict[str, Any]], None], expected: str) -> None:
    """An invalid field is reported with its location and the rule it breaks."""
    data = copy.deepcopy(VALID)
    change(data)
    details = _details(_encode(data))
    assert any(detail.startswith(expected) for detail in details), details


def test_every_problem_is_reported_at_once() -> None:
    """A person fixes a protocol in one pass, not one error per run."""
    data = copy.deepcopy(VALID)
    data["title"] = ""
    data["criteria"][0]["code"] = "bad"
    details = _details(_encode(data))
    assert len(details) == 2


def test_the_digest_is_over_the_exact_bytes() -> None:
    """Anyone can recompute it; a changed line ending is a changed protocol."""
    data = _encode(VALID)
    assert protocol_digest(data) == hashlib.sha256(data).hexdigest()
    crlf = data.replace(b"\n", b"\r\n")
    assert parse_protocol(crlf, source="protocol.yaml") == parse_protocol(data, source="p")
    assert protocol_digest(crlf) != protocol_digest(data)


def test_a_byte_order_mark_is_accepted() -> None:
    """Some Windows editors add one; the content is still the same protocol."""
    protocol = parse_protocol(b"\xef\xbb\xbf" + _encode(VALID), source="protocol.yaml")
    assert protocol.review_id == "example"


def test_bytes_that_are_not_utf8_are_refused() -> None:
    """The protocol is text; anything else is named, with the offending byte."""
    with pytest.raises(ProtocolError, match="is not UTF-8 text"):
        parse_protocol(b"title: \xff\xfe\n", source="protocol.yaml")


def test_a_protocol_cannot_run_code() -> None:
    """``safe_load`` refuses Python tags: the protocol is data, never instructions."""
    with pytest.raises(ProtocolError, match="is not valid YAML"):
        parse_protocol(b"!!python/object/apply:os.system ['echo unsafe']\n", source="p.yaml")
