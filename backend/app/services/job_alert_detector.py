"""Rule-based detector for job alert emails."""

from __future__ import annotations

import re

_JOB_SENDER_DOMAINS: frozenset[str] = frozenset(
    [
        "linkedin.com",
        "indeed.com",
        "glassdoor.com",
        "naukri.com",
        "monster.com",
        "ziprecruiter.com",
        "dice.com",
        "wellfound.com",
        "levels.fyi",
        "simplyhired.com",
        "careerbuilder.com",
    ]
)

_JOB_SUBJECT_KEYWORDS: tuple[str, ...] = (
    "job alert",
    "new jobs",
    "jobs matching",
    "job opportunity",
    "career opportunity",
    "new opening",
    "we are hiring",
    "we're hiring",
    "jobs for you",
    "job matches",
    "job posting",
    "job recommendation",
)


class JobAlertDetector:
    """Stateless rule-based detector for job alert emails.

    Checks sender domain and subject/snippet for known job alert signals.
    No LLM calls — fast, private, deterministic.
    """

    def is_job_alert(
        self,
        subject: str,
        sender_email: str,
        snippet: str | None = None,
    ) -> bool:
        """Return True if the email looks like a job alert.

        Args:
            subject: Email subject line.
            sender_email: Sender email address (e.g. "jobs@linkedin.com").
            snippet: Optional short preview of the email body.

        Returns:
            True if this email matches job alert signals.
        """
        if self._matches_sender_domain(sender_email):
            return True
        if self._matches_keywords(subject):
            return True
        if snippet and self._matches_keywords(snippet):
            return True
        return False

    def _matches_sender_domain(self, sender_email: str) -> bool:
        # Strip display-name format: "Name <email@domain.com>" → "email@domain.com"
        angle_match = re.search(r"<([^>]+)>", sender_email)
        addr = angle_match.group(1) if angle_match else sender_email
        match = re.search(r"@([\w.\-]+)$", addr.lower())
        if not match:
            return False
        domain = match.group(1)
        # Check exact domain and parent domain (e.g. "mail.linkedin.com" -> "linkedin.com")
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            if candidate in _JOB_SENDER_DOMAINS:
                return True
        return False

    def _matches_keywords(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in _JOB_SUBJECT_KEYWORDS)
