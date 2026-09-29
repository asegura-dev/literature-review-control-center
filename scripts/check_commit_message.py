"""Reject commit messages that attribute authorship to anyone but the human author (ADR-0008).

Run by pre-commit as a ``commit-msg`` hook, with the path of the message being committed, and by
CI over every commit of a pull request, because a local hook can be skipped. Uses only the
standard library, so pre-commit can run it without the project's environment.

The patterns are generic and name no vendor. Every ``Co-authored-by`` trailer is rejected, human
ones included: LRCC has one author, and allowing named human co-authors is an amendment to
ADR-0008, not a quiet widening of a pattern here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: One pattern per kind of attribution, matched against each line, case-insensitively.
ATTRIBUTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("co-author trailer", re.compile(r"^\s*co-authored-by\s*:", re.IGNORECASE)),
    ("generated-with line", re.compile(r"\bgenerated\s+(with|by)\b", re.IGNORECASE)),
    ("session trailer", re.compile(r"^\s*[\w-]*session[\w-]*\s*:\s*\S", re.IGNORECASE)),
)


def find_attribution(message: str) -> list[str]:
    """Return one description per attributing line in ``message``.

    Lines git treats as comments (starting with ``#``) are ignored: they never reach the commit.

    Args:
        message: The full commit message.

    Returns:
        A description of each offending line, empty if the message is clean.
    """
    problems: list[str] = []
    for number, line in enumerate(message.splitlines(), start=1):
        if line.startswith("#"):
            continue
        for kind, pattern in ATTRIBUTION_PATTERNS:
            if pattern.search(line):
                problems.append(f"line {number}: {kind}: {line.strip()}")
    return problems


def main(paths: list[str]) -> int:
    """Check each message file and report every attributing line.

    Args:
        paths: Paths of files holding one commit message each.

    Returns:
        0 if every message is clean, 1 otherwise.
    """
    if not paths:
        print("usage: check_commit_message.py MESSAGE_FILE [MESSAGE_FILE ...]", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        problems = find_attribution(Path(path).read_text(encoding="utf-8"))
        for problem in problems:
            print(f"{path}: {problem}", file=sys.stderr)
        failed = failed or bool(problems)
    if failed:
        print(
            "Commit messages name only the human author (ADR-0008). Remove the lines above.",
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
