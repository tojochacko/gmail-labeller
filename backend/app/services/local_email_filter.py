"""Local email filter — classifies emails on-device before any cloud LLM call.

Rules are evaluated in order; the first match wins. If no rule matches, the email
proceeds to the normal LLM classification pipeline.

Note: attachment emails are excluded upstream at the Gmail query level
(`-has:attachment`) so they never reach this filter.

Adding a new rule:
    1. Implement the EmailRule Protocol.
    2. Append an instance to LocalEmailFilter._rules (or pass it in via the constructor).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Subjects that contain sensitive financial data — never shared with a cloud LLM.
# Comparison is case-insensitive substring match against the full subject string.
_SENSITIVE_SUBJECT_PATTERNS: list[str] = [
    "credit card statement",
    "bank statement",
]


@dataclass
class FilterResult:
    """Outcome of a local filter check."""

    skip_llm: bool
    label: str  # "Important" | "Not Important" — only meaningful when skip_llm is True
    reason: str  # Human-readable audit message


@runtime_checkable
class EmailRule(Protocol):
    """Protocol every local email rule must satisfy."""

    def check(self, email_row: dict) -> FilterResult | None:
        """Inspect *email_row* and return a FilterResult if the rule fires, else None.

        Args:
            email_row: Raw email dict as returned by SessionRepository.fetch_session_emails().

        Returns:
            FilterResult if this rule applies, None to pass control to the next rule.
        """
        ...


class SensitiveSubjectRule:
    """Emails whose subject matches a sensitive pattern are classified locally.

    Subject matching is case-insensitive substring search against the configured
    patterns. The default patterns cover common financial statement emails.
    """

    def __init__(self, patterns: list[str] | None = None) -> None:
        self._patterns = [p.lower() for p in (patterns or _SENSITIVE_SUBJECT_PATTERNS)]

    def check(self, email_row: dict) -> FilterResult | None:
        subject = (email_row.get("subject") or "").lower()
        for pattern in self._patterns:
            if pattern in subject:
                return FilterResult(
                    skip_llm=True,
                    label="Important",
                    reason=f"Subject matches sensitive pattern '{pattern}' — classified locally",
                )
        return None


class LocalEmailFilter:
    """Evaluate a prioritised list of rules against an email row.

    The first rule that returns a FilterResult wins. If no rule matches,
    returns a FilterResult(skip_llm=False) so the caller can proceed to the LLM.
    """

    def __init__(self, rules: list[EmailRule] | None = None) -> None:
        self._rules: list[EmailRule] = (
            [SensitiveSubjectRule()] if rules is None else rules
        )

    def check(self, email_row: dict) -> FilterResult:
        """Run all rules in priority order and return the first match.

        Args:
            email_row: Raw email dict from the database.

        Returns:
            FilterResult — always non-None. skip_llm=False means proceed to LLM.
        """
        for rule in self._rules:
            result = rule.check(email_row)
            if result is not None:
                logger.info(
                    "Local filter matched for email '%s': %s",
                    email_row.get("subject", "(no subject)"),
                    result.reason,
                )
                return result

        return FilterResult(skip_llm=False, label="", reason="No local rule matched")
