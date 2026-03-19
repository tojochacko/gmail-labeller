"""PII redaction service — strips personal data before sending prompts to cloud LLMs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Presidio entity types to redact from email content before cloud transmission.
# DATE_TIME is intentionally excluded: temporal context aids classification and is low-risk.
_ENTITIES_TO_REDACT = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "PERSON",
    "LOCATION",
    "URL",
    "CREDIT_CARD",
    "IBAN_CODE",
    "CRYPTO",
    "MEDICAL_LICENSE",
    "US_SSN",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "NRP",  # Nationality, religious, political group
]


@dataclass
class RedactionResult:
    """Result of a PII redaction pass."""

    text: str
    entities_found: int
    entity_counts: dict[str, int] = field(default_factory=dict)


class PIIRedactor:
    """Detect and replace PII in text using Microsoft Presidio.

    Uses lazy initialization — Presidio (and the spaCy model) is loaded on first use.
    Degrades gracefully to a no-op if presidio-analyzer is not installed.

    Usage:
        redactor = PIIRedactor()
        result = redactor.redact("Call me at 555-1234 or email john@example.com")
        # result.text → "Call me at <PHONE_NUMBER> or email <EMAIL_ADDRESS>"
    """

    def __init__(self) -> None:
        self._analyzer = None
        self._anonymizer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-load Presidio engines (spaCy model is loaded on first call)."""
        if self._initialized:
            return

        try:
            from presidio_analyzer import AnalyzerEngine, RecognizerRegistry  # type: ignore[import-untyped]
            from presidio_analyzer.nlp_engine import NlpEngineProvider  # type: ignore[import-untyped]
            from presidio_anonymizer import AnonymizerEngine  # type: ignore[import-untyped]

            # Build an English-only NLP engine.
            # Explicitly list spaCy entity types that have no Presidio equivalent in
            # labels_to_ignore so the model does not emit "not mapped" warnings for
            # CARDINAL, ORDINAL, QUANTITY, etc.
            nlp_engine = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
                    "ner_model_configuration": {
                        "labels_to_ignore": [
                            "CARDINAL",
                            "ORDINAL",
                            "QUANTITY",
                            "MONEY",
                            "PERCENT",
                            "WORK_OF_ART",
                            "EVENT",
                            "LANGUAGE",
                            "LAW",
                            "FAC",
                            "PRODUCT",
                        ],
                    },
                }
            ).create_engine()

            # Build an English-only recognizer registry so Presidio does not attempt
            # to register es/it/pl recognizers and emit "language not supported" warnings.
            registry = RecognizerRegistry(supported_languages=["en"])
            registry.load_predefined_recognizers(languages=["en"])

            self._analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                registry=registry,
                supported_languages=["en"],
            )
            self._anonymizer = AnonymizerEngine()
            logger.info("PII redaction engine initialized (presidio + en_core_web_lg)")
        except ImportError:
            logger.warning(
                "presidio-analyzer not installed — PII redaction is DISABLED. "
                "Run: uv add presidio-analyzer presidio-anonymizer && "
                "python -m spacy download en_core_web_lg"
            )

        self._initialized = True

    def redact(self, text: str) -> RedactionResult:
        """Replace PII entities in *text* with type-labelled placeholder tokens.

        The original values are discarded; they are never logged or stored.
        Entity type counts are logged at INFO level so callers can audit coverage.

        Args:
            text: Raw text that may contain PII (e.g. an email prompt).

        Returns:
            RedactionResult with the sanitised text and a summary of what was found.
        """
        self._ensure_initialized()

        if not text or not text.strip():
            return RedactionResult(text=text, entities_found=0)

        if self._analyzer is None or self._anonymizer is None:
            # Degraded mode: Presidio not available — pass through unchanged.
            return RedactionResult(text=text, entities_found=0)

        results = self._analyzer.analyze(
            text=text,
            entities=_ENTITIES_TO_REDACT,
            language="en",
        )

        if not results:
            return RedactionResult(text=text, entities_found=0)

        anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)

        entity_counts: dict[str, int] = {}
        for r in results:
            entity_counts[r.entity_type] = entity_counts.get(r.entity_type, 0) + 1

        logger.info("PII redacted before LLM call: %s", entity_counts)

        return RedactionResult(
            text=anonymized.text,
            entities_found=len(results),
            entity_counts=entity_counts,
        )
