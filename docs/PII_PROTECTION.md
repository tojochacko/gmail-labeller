# PII Protection in Pattern Learning

## Overview

Email content processed by the auto-labeling system may contain personal information —
names, addresses, medical terms, financial details. This document describes the layers
of protection in place to ensure that personal data is neither stored in the database
nor transmitted to cloud LLMs.

---

## Protection layers

### 1. Local filter (pre-LLM)

`local_email_filter.py` evaluates rule-based conditions before any LLM call is made.
Emails matching sensitive subject patterns (bank statements, transaction alerts, OTPs,
credit card statements) are classified locally and never sent to a cloud model.

### 2. Subject redaction before pattern storage

`LabelService._extract_patterns_after_labeling()` runs `PIIRedactor` on the email
subject **before** building the pattern extraction request. Any entity detected by
Presidio (names, locations, phone numbers, email addresses, etc.) is replaced with a
type placeholder (e.g. `<PERSON>`) before the subject reaches `PatternLearningService`.

This means the `label_patterns` table in Supabase only ever holds already-sanitised
tokens, not the original personal data.

### 3. Snippet excluded from pattern learning

Keyword extraction operates on the **subject line only**. Email body snippets are
intentionally excluded because they carry a higher density of personal content
(names in greetings, medical or financial detail in the body text) compared to
subject lines.

### 4. Personal domain filter

`PatternLearningService._extract_domain()` skips personal email provider domains
(`gmail.com`, `yahoo.com`, `icloud.com`, etc.). These domains carry no organisational
signal and their local parts (before the `@`) may encode personal names in some
provider setups. Only corporate/organisational domains are stored as patterns.

### 5. PII redaction before LLM call (defence-in-depth)

`AgentService.trigger_agent_run()` runs `PIIRedactor` on the fully assembled prompt —
including any learned context injected from stored patterns — immediately before the
call is dispatched to OpenAI or Ollama. This acts as a final safety net even if any
of the upstream guards are bypassed.

---

## Entities redacted by Presidio

The redactor targets the following entity types:

| Entity | Examples |
|---|---|
| `EMAIL_ADDRESS` | `john@example.com` |
| `PHONE_NUMBER` | `+1 555-1234` |
| `PERSON` | `John Smith` |
| `LOCATION` | `London`, `123 Main St` |
| `URL` | `https://example.com` |
| `CREDIT_CARD` | `4111 1111 1111 1111` |
| `IBAN_CODE` | `GB29 NWBK 6016 1331 9268 19` |
| `US_SSN` | `123-45-6789` |
| `US_PASSPORT` | `A12345678` |
| `CRYPTO` | wallet addresses |
| `MEDICAL_LICENSE` | licence numbers |
| `NRP` | nationality/religion/politics references |

`DATE_TIME` is intentionally **not** redacted — temporal context aids classification
and is considered low-risk.

---

## One-time DB migration

Patterns written before the subject-redaction guard was introduced may contain
unredacted values. The migration script scans all existing keyword pattern rows and
deletes any whose value contains a Presidio placeholder after re-redaction:

```bash
uv run python -m backend.scripts.redact_existing_patterns
```

Domain patterns are not affected (they are organisational identifiers).

---

## Relevant files

| File | Role |
|---|---|
| `backend/app/services/pii_redactor.py` | Presidio-backed redaction engine |
| `backend/app/services/label_service.py` | Redacts subject before pattern extraction |
| `backend/app/services/pattern_learning_service.py` | Subject-only keywords, personal domain filter |
| `backend/app/services/local_email_filter.py` | Blocks sensitive emails before LLM |
| `backend/app/services/agent_service.py` | Final redaction pass before LLM call |
| `backend/scripts/redact_existing_patterns.py` | One-time DB migration |
| `backend/tests/test_pii_pattern_guard.py` | Tests for all pattern-level PII guards |
| `backend/tests/test_pii_redactor.py` | Tests for the redaction engine |
