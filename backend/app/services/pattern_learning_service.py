"""Service for learning patterns from labeled emails."""

import logging
import re
from collections import Counter
from typing import Optional
from uuid import UUID

from ..schemas.label_patterns import (
    LearnedContext,
    PatternExtractionRequest,
)
from .supabase_service import SupabaseService

logger = logging.getLogger(__name__)


class PatternLearningService:
    """Extract and manage learned patterns from labeled emails."""

    # Common stop words to exclude from keyword extraction
    STOP_WORDS = {
        "the",
        "be",
        "to",
        "of",
        "and",
        "a",
        "in",
        "that",
        "have",
        "i",
        "it",
        "for",
        "not",
        "on",
        "with",
        "he",
        "as",
        "you",
        "do",
        "at",
        "this",
        "but",
        "his",
        "by",
        "from",
        "they",
        "we",
        "say",
        "her",
        "she",
        "or",
        "an",
        "will",
        "my",
        "one",
        "all",
        "would",
        "there",
        "their",
        "what",
        "so",
        "up",
        "out",
        "if",
        "about",
        "who",
        "get",
        "which",
        "go",
        "me",
        "when",
        "make",
        "can",
        "like",
        "time",
        "no",
        "just",
        "him",
        "know",
        "take",
        "people",
        "into",
        "year",
        "your",
        "good",
        "some",
        "could",
        "them",
        "see",
        "other",
        "than",
        "then",
        "now",
        "look",
        "only",
        "come",
        "its",
        "over",
        "think",
        "also",
        "back",
        "after",
        "use",
        "two",
        "how",
        "our",
        "work",
        "first",
        "well",
        "way",
        "even",
        "new",
        "want",
        "because",
        "any",
        "these",
        "give",
        "day",
        "most",
        "us",
        "is",
        "was",
        "are",
        "been",
        "has",
        "had",
        "were",
        "said",
        "did",
        "having",
    }

    # Minimum word length for keywords
    MIN_KEYWORD_LENGTH = 4

    # Maximum keywords to extract per email
    MAX_KEYWORDS_PER_EMAIL = 5

    def __init__(self, supabase: SupabaseService):
        """Initialize pattern learning service."""
        self._supabase = supabase

    async def extract_and_store_patterns(
        self, request: PatternExtractionRequest, user_id: UUID
    ) -> dict[str, int]:
        """
        Extract patterns from labeled email and store them.

        Args:
            request: Pattern extraction request containing email data
            user_id: User ID for pattern ownership

        Returns:
            Dictionary with counts of patterns added: {"domains": 1, "keywords": 3}
        """
        patterns_added = {"domains": 0, "keywords": 0}

        # Extract domain
        domain = self._extract_domain(request.sender_email)
        if domain:
            await self._upsert_pattern(
                user_id=user_id,
                label_type=request.label,
                pattern_type="domain",
                pattern_value=domain,
            )
            patterns_added["domains"] = 1

        # Extract keywords
        keywords = self._extract_keywords(request.email_subject, request.email_snippet)
        for keyword in keywords:
            await self._upsert_pattern(
                user_id=user_id,
                label_type=request.label,
                pattern_type="keyword",
                pattern_value=keyword,
            )
        patterns_added["keywords"] = len(keywords)

        logger.info(
            f"Extracted {patterns_added['domains']} domains and "
            f"{patterns_added['keywords']} keywords for user {user_id}"
        )

        return patterns_added

    def _extract_domain(self, email: str) -> Optional[str]:
        """
        Extract domain from email address.

        Args:
            email: Email address (e.g., "user@example.com")

        Returns:
            Domain name (e.g., "example.com") or None if invalid
        """
        match = re.search(r"@([\w\.-]+)", email)
        if match:
            return match.group(1).lower()
        return None

    def _extract_keywords(self, subject: str, snippet: Optional[str] = None) -> list[str]:
        """
        Extract meaningful keywords from email content.

        Args:
            subject: Email subject line
            snippet: Email snippet/preview

        Returns:
            List of top keywords (max MAX_KEYWORDS_PER_EMAIL)
        """
        # Combine subject and snippet
        text = subject or ""
        if snippet:
            text += " " + snippet

        # Normalize: lowercase and remove special characters
        text = re.sub(r"[^\w\s]", " ", text.lower())

        # Tokenize and filter
        words = text.split()
        filtered_words = [
            word
            for word in words
            if len(word) >= self.MIN_KEYWORD_LENGTH
            and word not in self.STOP_WORDS
            and not word.isdigit()
        ]

        # Count frequency and take top N
        word_counts = Counter(filtered_words)
        top_keywords = [word for word, _ in word_counts.most_common(self.MAX_KEYWORDS_PER_EMAIL)]

        return top_keywords

    async def _upsert_pattern(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> None:
        """
        Insert or update a pattern (increment occurrence).

        Args:
            user_id: User ID for pattern ownership
            label_type: "Important" or "Not Important"
            pattern_type: "domain" or "keyword"
            pattern_value: The pattern value
        """
        await self._supabase.upsert_label_pattern(
            user_id=user_id,
            label_type=label_type,
            pattern_type=pattern_type,
            pattern_value=pattern_value,
        )

    async def get_learned_context(self, user_id: UUID) -> LearnedContext:
        """
        Retrieve all learned patterns for a user, formatted for prompts.

        Args:
            user_id: User ID

        Returns:
            LearnedContext with patterns organized by type and label
        """
        patterns = await self._supabase.get_label_patterns(user_id=user_id)

        context = LearnedContext()

        for pattern in patterns:
            if pattern["label_type"] == "Important":
                if pattern["pattern_type"] == "domain":
                    context.important_domains.append(pattern["pattern_value"])
                elif pattern["pattern_type"] == "keyword":
                    context.important_keywords.append(pattern["pattern_value"])
            elif pattern["label_type"] == "Not Important":
                if pattern["pattern_type"] == "domain":
                    context.not_important_domains.append(pattern["pattern_value"])
                elif pattern["pattern_type"] == "keyword":
                    context.not_important_keywords.append(pattern["pattern_value"])

        return context

    async def get_patterns_by_label(self, user_id: UUID, label_type: str) -> dict[str, list[str]]:
        """
        Get patterns grouped by type for a specific label.

        Args:
            user_id: User ID
            label_type: "Important" or "Not Important"

        Returns:
            Dictionary with "domains" and "keywords" lists
        """
        patterns = await self._supabase.get_label_patterns(user_id=user_id, label_type=label_type)

        result = {"domains": [], "keywords": []}

        for pattern in patterns:
            if pattern["pattern_type"] == "domain":
                result["domains"].append(pattern["pattern_value"])
            elif pattern["pattern_type"] == "keyword":
                result["keywords"].append(pattern["pattern_value"])

        return result
