"""One-time migration: redact PII from existing keyword patterns in label_patterns table.

Patterns written before the pre-redaction guard was added may contain person names or
other PII extracted from email subjects/snippets.  This script:

  1. Fetches every keyword pattern row for all users.
  2. Runs the value through PIIRedactor.
  3. Deletes any row whose redacted value contains a Presidio placeholder (e.g. <PERSON>),
     meaning the stored token was a PII entity.
  4. Logs a summary.

Usage:
    uv run python -m backend.scripts.redact_existing_patterns

Environment variables required (same as the main app):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, FERNET_SECRET_KEY,
    GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI,
    GOOGLE_OAUTH_SCOPE
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Presidio placeholder marker — any redacted value containing this was a PII entity.
_PII_PLACEHOLDER_MARKER = "<"


async def run() -> None:
    from backend.app.config import Settings
    from backend.app.services.pii_redactor import PIIRedactor
    from backend.app.services.supabase_service import SupabaseService

    settings = Settings()  # type: ignore[call-arg]  # reads from environment
    supabase = SupabaseService(settings)
    redactor = PIIRedactor()

    logger.info("Fetching all keyword patterns from label_patterns …")

    # Fetch all keyword patterns (domain patterns are organisational identifiers,
    # not at risk, so we skip them).
    response = (
        supabase.client.table("label_patterns")
        .select("pattern_id, user_id, pattern_value, label_type")
        .eq("pattern_type", "keyword")
        .execute()
    )

    rows = response.data or []
    logger.info("Found %d keyword pattern rows to inspect.", len(rows))

    deleted = 0
    kept = 0

    for row in rows:
        value: str = row["pattern_value"]
        result = redactor.redact(value)

        if _PII_PLACEHOLDER_MARKER in result.text:
            # The stored keyword was (or contained) a PII entity — remove it.
            supabase.client.table("label_patterns").delete().eq(
                "pattern_id", row["pattern_id"]
            ).execute()
            logger.info(
                "DELETED pattern pattern_id=%s value=%r → redacted to %r (user=%s label=%s)",
                row["pattern_id"],
                value,
                result.text,
                row["user_id"],
                row["label_type"],
            )
            deleted += 1
        else:
            kept += 1

    logger.info(
        "Migration complete. Rows inspected: %d | deleted (PII): %d | kept: %d",
        len(rows),
        deleted,
        kept,
    )


if __name__ == "__main__":
    asyncio.run(run())
