"""Text rules from CLAUDE.md, enforced at publish time. A violation blocks the prediction."""

from __future__ import annotations

import re

BANNED_TERMS: tuple[str, ...] = (
    "buy",
    "sell",
    "hold",
    "accumulate",
    "short",
    "long",
    "target price",
    "price target",
)

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in BANNED_TERMS) + r")\b",
    flags=re.IGNORECASE,
)

DISCLAIMER = (
    "fibr0 publishes research-derived likelihoods, not investment advice. "
    "It does not recommend buying or selling any security. Track record: fibr0.com/calibration"
)


def find_banned(text: str) -> list[str]:
    """Return the distinct banned terms present in `text`, lower-cased, in order of appearance."""
    seen: list[str] = []
    for match in _PATTERN.finditer(text):
        term = match.group(1).lower()
        if term not in seen:
            seen.append(term)
    return seen


def is_publishable(text: str) -> bool:
    return not find_banned(text)
