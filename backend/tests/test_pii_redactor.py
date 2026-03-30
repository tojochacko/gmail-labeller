"""Tests for the PIIRedactor service."""

from __future__ import annotations

import pytest

from backend.app.services.pii_redactor import PIIRedactor, RedactionResult


@pytest.fixture
def redactor() -> PIIRedactor:
    return PIIRedactor()


class TestRedactionResult:
    def test_empty_text_returns_unchanged(self, redactor: PIIRedactor) -> None:
        result = redactor.redact("")
        assert result.text == ""
        assert result.entities_found == 0

    def test_whitespace_only_returns_unchanged(self, redactor: PIIRedactor) -> None:
        result = redactor.redact("   ")
        assert result.text == "   "
        assert result.entities_found == 0

    def test_clean_text_returns_unchanged(self, redactor: PIIRedactor) -> None:
        text = "Please classify this email as Important or Not Important."
        result = redactor.redact(text)
        assert result.text == text
        assert result.entities_found == 0


class TestEmailRedaction:
    def test_email_address_is_replaced(self, redactor: PIIRedactor) -> None:
        text = "From: alice@example.com\nSubject: Meeting tomorrow"
        result = redactor.redact(text)
        assert "alice@example.com" not in result.text
        assert result.entities_found > 0

    def test_email_placeholder_present(self, redactor: PIIRedactor) -> None:
        text = "Reply to john.doe@company.org for details."
        result = redactor.redact(text)
        assert "john.doe@company.org" not in result.text
        assert "EMAIL_ADDRESS" in result.entity_counts

    def test_multiple_emails_all_replaced(self, redactor: PIIRedactor) -> None:
        text = "CC: alice@foo.com, bob@bar.com"
        result = redactor.redact(text)
        assert "alice@foo.com" not in result.text
        assert "bob@bar.com" not in result.text
        assert result.entity_counts.get("EMAIL_ADDRESS", 0) >= 2


class TestPhoneRedaction:
    def test_phone_number_is_replaced(self, redactor: PIIRedactor) -> None:
        text = "Call me at +1-800-555-0199 to confirm."
        result = redactor.redact(text)
        assert "+1-800-555-0199" not in result.text
        assert result.entities_found > 0


class TestPromptIntegrity:
    def test_classification_instruction_preserved(self, redactor: PIIRedactor) -> None:
        """The LLM instruction structure must survive redaction."""
        text = (
            "Subject: Invoice from Alice Smith\n"
            "From: alice@acme.com\n"
            "Snippet: Please find attached the invoice.\n\n"
            "Classify this email as 'Important' or 'Not Important'.\n"
            'Respond in JSON: {"suggestion": "Important|Not Important", '
            '"confidence": 0.0-1.0, "reasoning": "..."}'
        )
        result = redactor.redact(text)
        assert "Classify this email" in result.text
        assert "Important" in result.text
        assert "Not Important" in result.text
        assert "confidence" in result.text
        assert "alice@acme.com" not in result.text

    def test_returns_redaction_result_type(self, redactor: PIIRedactor) -> None:
        result = redactor.redact("Contact us at support@example.com")
        assert isinstance(result, RedactionResult)
        assert isinstance(result.text, str)
        assert isinstance(result.entities_found, int)
        assert isinstance(result.entity_counts, dict)


class TestLazyInitialization:
    def test_redactor_initializes_on_first_call(self) -> None:
        """Presidio engines must not be loaded at construction time."""
        r = PIIRedactor()
        assert not r._initialized
        r.redact("hello")
        assert r._initialized

    def test_subsequent_calls_reuse_engine(self, redactor: PIIRedactor) -> None:
        redactor.redact("first call at test@example.com")
        analyzer_ref = redactor._analyzer
        redactor.redact("second call at test@example.com")
        assert redactor._analyzer is analyzer_ref


class TestIsAvailable:
    def test_is_available_returns_false_when_presidio_absent(
        self, monkeypatch,
    ) -> None:
        """is_available returns False when presidio_analyzer cannot be imported."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name.startswith("presidio"):
                raise ImportError("presidio not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        redactor = PIIRedactor()
        assert redactor.is_available() is False

    def test_is_available_returns_true_when_presidio_present(self) -> None:
        """is_available returns True when Presidio loads successfully."""
        redactor = PIIRedactor()
        # This test is skipped if presidio is not installed in the test environment.
        try:
            import presidio_analyzer  # noqa: F401
        except ImportError:
            pytest.skip("presidio-analyzer not installed")
        assert redactor.is_available() is True
