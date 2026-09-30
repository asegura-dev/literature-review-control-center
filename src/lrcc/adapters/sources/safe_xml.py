"""Reading the XML sources answer with, safely (ADR-0011).

``defusedxml`` refuses documents that declare entities or fetch external ones, so an answer
cannot expand into gigabytes or read a local file. What a source returns is data, never trusted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from lrcc.domain.errors import SourceError

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


def parse_xml(data: bytes, source: str) -> Element:
    """Parse an XML answer.

    Args:
        data: The response body.
        source: The source's name, for the error.

    Returns:
        The root element.

    Raises:
        SourceError: If the document is malformed, or declares entities.
    """
    try:
        return ElementTree.fromstring(data)
    except (ElementTree.ParseError, DefusedXmlException) as problem:
        raise SourceError(
            f"{source} answered with XML that cannot be read safely",
            [f"{type(problem).__name__}: {problem}"],
        ) from None


def clean(text: str | None) -> str:
    """Collapse whitespace, so a title broken over lines becomes one line.

    Args:
        text: Text from an element, or None if the element was absent.

    Returns:
        The text with runs of whitespace replaced by single spaces, or an empty string.
    """
    return " ".join((text or "").split())


def full_text(node: Element | None) -> str:
    """Return all the text inside an element, inline markup such as ``<i>`` included.

    Args:
        node: The element, or None if it was absent.

    Returns:
        Its text, cleaned, or an empty string.
    """
    return clean("".join(node.itertext())) if node is not None else ""
