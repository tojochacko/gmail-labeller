"""Tests for the LocalEmailFilter rule engine."""

from __future__ import annotations

import pytest

from backend.app.services.local_email_filter import (
    FilterResult,
    LocalEmailFilter,
    SensitiveSubjectRule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email(subject: str = "Hello") -> dict:
    return {"subject": subject}


# ---------------------------------------------------------------------------
# SensitiveSubjectRule
# ---------------------------------------------------------------------------

class TestSensitiveSubjectRule:
    def setup_method(self) -> None:
        self.rule = SensitiveSubjectRule()

    def test_fires_on_credit_card_statement(self) -> None:
        result = self.rule.check(_email(subject="Your Credit Card Statement for March"))
        assert result is not None
        assert result.skip_llm is True
        assert result.label == "Important"

    def test_fires_on_bank_statement(self) -> None:
        result = self.rule.check(_email(subject="Bank Statement - February 2026"))
        assert result is not None
        assert result.skip_llm is True

    def test_case_insensitive_match(self) -> None:
        assert self.rule.check(_email(subject="CREDIT CARD STATEMENT")) is not None
        assert self.rule.check(_email(subject="bank statement")) is not None

    def test_partial_subject_match(self) -> None:
        assert self.rule.check(_email(subject="Re: bank statement enclosed")) is not None

    def test_does_not_fire_on_unrelated_subject(self) -> None:
        assert self.rule.check(_email(subject="Meeting tomorrow at 9am")) is None

    def test_does_not_fire_on_empty_subject(self) -> None:
        assert self.rule.check(_email(subject="")) is None

    def test_does_not_fire_when_subject_absent(self) -> None:
        assert self.rule.check({}) is None

    def test_custom_patterns(self) -> None:
        rule = SensitiveSubjectRule(patterns=["tax return"])
        assert rule.check(_email(subject="Your tax return is ready")) is not None
        assert rule.check(_email(subject="Credit Card Statement")) is None


# ---------------------------------------------------------------------------
# LocalEmailFilter (engine)
# ---------------------------------------------------------------------------

class TestLocalEmailFilter:
    def setup_method(self) -> None:
        self.filter = LocalEmailFilter()

    def test_returns_filter_result_type(self) -> None:
        result = self.filter.check(_email())
        assert isinstance(result, FilterResult)

    def test_no_rule_matches_returns_skip_false(self) -> None:
        result = self.filter.check(_email(subject="Hey, lunch tomorrow?"))
        assert result.skip_llm is False

    def test_sensitive_subject_fires(self) -> None:
        result = self.filter.check(_email(subject="Your Bank Statement is ready"))
        assert result.skip_llm is True
        assert result.label == "Important"

    def test_custom_rules_respected(self) -> None:
        class AlwaysBlock:
            def check(self, email_row: dict) -> FilterResult | None:
                return FilterResult(skip_llm=True, label="Not Important", reason="always")

        f = LocalEmailFilter(rules=[AlwaysBlock()])
        result = f.check(_email(subject="Normal email"))
        assert result.skip_llm is True
        assert result.label == "Not Important"

    def test_empty_rules_list_passes_through(self) -> None:
        f = LocalEmailFilter(rules=[])
        result = f.check(_email(subject="Credit Card Statement"))
        assert result.skip_llm is False
