"""Batch email classification orchestrator."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from ..schemas.agent import AgentRunRequest
from .agent_service import AgentService
from .db_service import DBService
from .gmail_toolkit import GmailService
from .job_alert_detector import JobAlertDetector
from .local_email_filter import LocalEmailFilter
from .session_repository import SessionRepository


logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of a batch classification run."""

    session_id: UUID
    total: int
    classified: int
    failed: int


class BatchClassifier:
    """Orchestrate sequential LLM classification for all emails in a session."""

    def __init__(
        self,
        session_repo: SessionRepository,
        db: DBService,
        agent_service: AgentService,
        gmail_service: GmailService,
        email_filter: LocalEmailFilter | None = None,
        job_alert_detector: JobAlertDetector | None = None,
    ) -> None:
        self._repo = session_repo
        self._supabase = db  # alias kept to avoid wider rename in run_batch
        self._agent_service = agent_service
        self._gmail_service = gmail_service
        self._email_filter = email_filter or LocalEmailFilter()
        self._job_alert_detector = job_alert_detector or JobAlertDetector()

    async def run_batch(self, session_id: UUID, user_id: UUID) -> BatchResult:
        """Classify all unlabeled emails in the session sequentially.

        Steps for each email:
        1. Trigger agent classification (patterns auto-injected by AgentService)
        2. Apply the resulting Gmail label via GmailService
        3. Log progress

        After all emails are processed, marks session as awaiting_review.

        Args:
            session_id: Session UUID
            user_id: User UUID

        Returns:
            BatchResult with counts
        """
        await self._repo.update_session_status(session_id, status="classifying")

        emails = await self._repo.fetch_session_emails(session_id)
        total = len(emails)
        classified = 0
        failed = 0

        logger.info("Batch classify session %s: %d emails", session_id, total)

        tokens = await self._supabase.fetch_gmail_tokens(user_id)

        for email_row in emails:
            email_id_str = email_row.get("id")
            gmail_message_id = email_row.get("gmail_message_id")
            subject = email_row.get("subject", "(no subject)")

            if not email_id_str or not gmail_message_id:
                logger.warning("Skipping email row missing id or gmail_message_id: %s", email_row)
                failed += 1
                continue

            try:
                from uuid import UUID as _UUID

                email_id = _UUID(email_id_str)

                # Check local rules first — may skip the LLM entirely.
                llm_is_job_alert = False
                filter_result = self._email_filter.check(email_row)
                if filter_result.skip_llm:
                    suggestion = filter_result.label
                    logger.info(
                        "[%d/%d] Local filter: '%s' → %s (%s)",
                        classified + 1,
                        total,
                        subject[:50],
                        suggestion,
                        filter_result.reason,
                    )
                else:
                    # Build classification prompt from email fields
                    prompt = _build_classification_prompt(email_row)
                    logger.debug("Built prompt for email_id=%s", email_id_str)

                    run = await self._agent_service.trigger_agent_run(
                        AgentRunRequest(
                            user_id=user_id,
                            email_id=email_id,
                            gmail_message_id=gmail_message_id,
                            prompt=prompt,
                            batch_run_id=session_id,
                        )
                    )

                    # Fetch result to get the suggestion
                    result = await self._agent_service.get_agent_run(run.run_id)
                    suggestion = None
                    if result and result.result_payload:
                        suggestion = result.result_payload.get("suggestion")
                        llm_is_job_alert = bool(result.result_payload.get("is_job_alert", False))
                        logger.debug(
                            "LLM response for email_id=%s: %s",
                            email_id_str,
                            result.result_payload,
                        )

                # Apply Gmail label if we have tokens and a suggestion
                if tokens and suggestion in ("Important", "Not Important"):
                    try:
                        await self._gmail_service.apply_label(
                            message_id=gmail_message_id,
                            label_id=suggestion,
                            tokens=tokens,
                            user_id=str(user_id),
                        )
                        logger.debug("Applied '%s' to Gmail msg %s", suggestion, gmail_message_id)
                    except Exception as label_err:
                        logger.warning(
                            "Failed to apply Gmail label for %s: %s", gmail_message_id, label_err
                        )

                # Apply ai-job-alert tag if detected by rule-based detector or LLM
                rule_based_job_alert = self._job_alert_detector.is_job_alert(
                    subject=email_row.get("subject", ""),
                    sender_email=email_row.get("sender_email", ""),
                    snippet=email_row.get("snippet") or "",
                )
                if tokens and (rule_based_job_alert or llm_is_job_alert):
                    try:
                        await self._gmail_service.apply_label(
                            message_id=gmail_message_id,
                            label_id="ai-job-alert",
                            tokens=tokens,
                            user_id=str(user_id),
                        )
                        logger.info("Applied 'ai-job-alert' tag to %s", gmail_message_id)
                    except Exception as tag_err:
                        logger.warning(
                            "Failed to apply ai-job-alert tag for %s: %s",
                            gmail_message_id,
                            tag_err,
                        )

                classified += 1
                logger.info(
                    "[%d/%d] Classified '%s' → %s", classified, total, subject[:50], suggestion
                )

            except Exception as e:
                failed += 1
                logger.error("Failed to classify email %s: %s", email_id_str, e)

            # Pause between LLM calls to avoid rate limiting
            if classified + failed < total:
                await asyncio.sleep(15)

        await self._repo.update_session_status(session_id, status="awaiting_review")
        logger.info(
            "Batch done for session %s: %d classified, %d failed", session_id, classified, failed
        )
        return BatchResult(
            session_id=session_id, total=total, classified=classified, failed=failed
        )


def _build_classification_prompt(email_row: dict) -> str:
    """Build a classification prompt from an email DB row.

    Args:
        email_row: Raw email dict from Supabase

    Returns:
        Prompt string for the LLM
    """
    subject = email_row.get("subject", "(no subject)")
    snippet = email_row.get("snippet", "")
    sender = email_row.get("sender_email", "unknown")
    return (
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"Snippet: {snippet}\n\n"
        "Classify this email as 'Important' or 'Not Important'.\n"
        "Also determine if this is a job posting, recruiter outreach, or automated job board alert.\n"
        'Respond in JSON: {"suggestion": "Important|Not Important", '
        '"confidence": 0.0-1.0, "reasoning": "...", "is_job_alert": true|false}'
    )
