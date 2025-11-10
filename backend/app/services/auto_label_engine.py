"""Auto-labeling engine for intelligent email categorization.

This service implements pattern-based auto-labeling with confidence scoring
and learning from user corrections (re-marks).

Scoring Algorithm:
- Domain match: 50% weight
- Keyword match: 30% weight (subject + snippet)
- Subject pattern: 20% weight
- Pattern weights: 1.0-5.0 multiplier (2.0 for re-marks)
- Confidence threshold: 0.4 (40%) for auto-labeling

Learning Loop:
- User re-marks update pattern weights (2x multiplier)
- Pattern usage tracked via times_applied
- Corrections tracked via times_corrected
- Confidence scores adjusted based on success rate
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional
from uuid import UUID

from ..schemas.email import EmailItem, LabelType
from .supabase_service import SupabaseService

logger = logging.getLogger(__name__)


# Configuration constants
CONFIDENCE_THRESHOLD = 0.4  # 40% minimum confidence for auto-labeling
DOMAIN_WEIGHT = 0.50  # 50% weight for domain matches
KEYWORD_WEIGHT = 0.30  # 30% weight for keyword matches
SUBJECT_WEIGHT = 0.20  # 20% weight for subject pattern matches
REMARK_MULTIPLIER = 2.0  # 2x weight for re-marked patterns


@dataclass
class LabelSuggestion:
    """Auto-labeling suggestion with confidence score."""

    label: LabelType
    confidence: float
    matched_patterns: list[str]  # List of pattern values that matched
    source: Literal["auto"] = "auto"


@dataclass
class PatternMatch:
    """Internal representation of a pattern match."""

    pattern_id: UUID
    pattern_type: str  # domain, keyword, subject
    pattern_value: str
    label_type: LabelType
    base_confidence: float
    pattern_weight: float
    weighted_score: float


class AutoLabelEngine:
    """Engine for pattern-based auto-labeling of emails."""

    def __init__(
        self, supabase: SupabaseService, confidence_threshold: float = CONFIDENCE_THRESHOLD
    ):
        """Initialize auto-labeling engine.

        Args:
            supabase: Supabase service for database operations
            confidence_threshold: Minimum confidence (0.0-1.0) for auto-labeling
        """
        self._supabase = supabase
        self._confidence_threshold = confidence_threshold

    async def suggest_label(
        self,
        email: EmailItem,
        user_id: UUID,
    ) -> Optional[LabelSuggestion]:
        """Suggest a label for an email based on learned patterns.

        Args:
            email: Email to label
            user_id: User UUID for pattern lookup

        Returns:
            LabelSuggestion if confidence >= threshold, None otherwise
        """
        logger.debug(
            f"🤖 AUTO-LABEL: Analyzing email {email.gmail_message_id} "
            f"(sender: {email.sender_email}, subject: '{email.subject[:50]}...')"
        )

        # Load user's learned patterns
        patterns = await self._load_patterns(user_id)
        if not patterns:
            logger.debug("No learned patterns found for user - skipping auto-label")
            return None

        # Find matching patterns for this email
        matches = self._find_matches(email, patterns)
        if not matches:
            logger.debug("No pattern matches found - email is Uncategorized")
            return None

        # Calculate confidence scores for each label
        important_score = self._calculate_score(
            matches=[m for m in matches if m.label_type == "Important"]
        )
        not_important_score = self._calculate_score(
            matches=[m for m in matches if m.label_type == "Not Important"]
        )

        logger.debug(
            f"📊 Confidence scores: Important={important_score:.3f}, "
            f"Not Important={not_important_score:.3f}"
        )

        # Determine winning label
        label: LabelType
        if important_score > not_important_score and important_score >= self._confidence_threshold:
            label = "Important"
            confidence = important_score
            matched = [m for m in matches if m.label_type == "Important"]
        elif not_important_score >= self._confidence_threshold:
            label = "Not Important"
            confidence = not_important_score
            matched = [m for m in matches if m.label_type == "Not Important"]
        else:
            logger.debug(
                f"⚠️  Confidence below threshold ({self._confidence_threshold:.2f}) "
                f"- email is Uncategorized"
            )
            return None

        suggestion = LabelSuggestion(
            label=label,
            confidence=confidence,
            matched_patterns=[m.pattern_value for m in matched],
        )

        logger.info(
            f"✅ AUTO-LABEL: {label} (confidence: {confidence:.3f}, "
            f"matched: {', '.join(suggestion.matched_patterns)})"
        )

        return suggestion

    async def record_pattern_usage(
        self,
        pattern_ids: list[UUID],
        was_correct: bool,
    ) -> None:
        """Record pattern usage and update statistics.

        Args:
            pattern_ids: List of pattern IDs that were used
            was_correct: Whether the auto-label was correct (user didn't re-mark)
        """
        for pattern_id in pattern_ids:
            await self._supabase.increment_pattern_usage(
                pattern_id=pattern_id,
                was_corrected=not was_correct,
            )

    async def update_pattern_on_remark(
        self,
        email: EmailItem,
        new_label: LabelType,
        user_id: UUID,
    ) -> None:
        """Update patterns when user re-marks an email.

        This applies 2x weight to patterns matching the new label to accelerate learning.

        Args:
            email: Email that was re-marked
            new_label: New label applied by user
            user_id: User UUID
        """
        logger.info(
            f"📝 RE-MARK: Updating patterns for email {email.gmail_message_id} → {new_label}"
        )

        # Extract patterns from the email
        if email.sender_domain:
            await self._supabase.upsert_pattern(
                user_id=user_id,
                pattern_type="domain",
                pattern_value=email.sender_domain,
                label_type=new_label,
                weight_multiplier=REMARK_MULTIPLIER,  # 2x weight for re-marks
            )

        # Extract keywords from subject
        if email.subject:
            keywords = self._extract_keywords(email.subject)
            for keyword in keywords:
                await self._supabase.upsert_pattern(
                    user_id=user_id,
                    pattern_type="keyword",
                    pattern_value=keyword,
                    label_type=new_label,
                    weight_multiplier=REMARK_MULTIPLIER,
                )

        logger.info(f"✅ Patterns updated with {REMARK_MULTIPLIER}x weight for re-mark")

    def _find_matches(self, email: EmailItem, patterns: list[dict]) -> list[PatternMatch]:
        """Find all patterns that match this email.

        Args:
            email: Email to match against
            patterns: List of learned patterns from database

        Returns:
            List of pattern matches with scores
        """
        matches = []

        for pattern in patterns:
            pattern_type = pattern["pattern_type"]
            pattern_value = pattern["pattern_value"].lower()
            label_type = pattern["label_type"]
            base_confidence = pattern["confidence_score"]
            pattern_weight = pattern.get("pattern_weight", 1.0)

            matched = False

            # Domain matching
            if pattern_type == "domain" and email.sender_domain:
                if email.sender_domain.lower() == pattern_value:
                    matched = True
                    type_weight = DOMAIN_WEIGHT

            # Keyword matching (subject + snippet)
            elif pattern_type == "keyword":
                text = " ".join(filter(None, [email.subject, email.snippet])).lower()
                if pattern_value in text:
                    matched = True
                    type_weight = KEYWORD_WEIGHT

            # Subject pattern matching
            elif pattern_type == "subject":
                if email.subject and pattern_value in email.subject.lower():
                    matched = True
                    type_weight = SUBJECT_WEIGHT

            if matched:
                # Calculate weighted score: base_confidence * type_weight * pattern_weight
                weighted_score = base_confidence * type_weight * pattern_weight

                matches.append(
                    PatternMatch(
                        pattern_id=pattern["pattern_id"],
                        pattern_type=pattern_type,
                        pattern_value=pattern_value,
                        label_type=label_type,
                        base_confidence=base_confidence,
                        pattern_weight=pattern_weight,
                        weighted_score=weighted_score,
                    )
                )

                logger.debug(
                    f"✓ Matched {pattern_type}='{pattern_value}' → {label_type} "
                    f"(base={base_confidence:.2f}, weight={pattern_weight:.1f}x, "
                    f"score={weighted_score:.3f})"
                )

        return matches

    def _calculate_score(self, matches: list[PatternMatch]) -> float:
        """Calculate overall confidence score from pattern matches.

        Uses weighted average of all matching patterns.

        Args:
            matches: List of pattern matches for a single label

        Returns:
            Confidence score (0.0-1.0)
        """
        if not matches:
            return 0.0

        # Sum weighted scores
        total_score = sum(m.weighted_score for m in matches)

        # Normalize by total possible weight
        # (If all pattern types matched with 1.0 confidence and 1.0 weight)
        max_possible = DOMAIN_WEIGHT + KEYWORD_WEIGHT + SUBJECT_WEIGHT

        # Cap at 1.0
        return min(total_score / max_possible, 1.0)

    def _extract_keywords(self, text: str, min_length: int = 4) -> list[str]:
        """Extract meaningful keywords from text.

        Args:
            text: Text to extract keywords from
            min_length: Minimum keyword length

        Returns:
            List of normalized keywords
        """
        # Remove special characters and split
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())

        # Filter out common stop words and short words
        stop_words = {
            "the",
            "is",
            "at",
            "which",
            "on",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "with",
            "to",
            "for",
            "of",
            "as",
            "by",
            "from",
            "that",
            "this",
            "your",
            "you",
            "have",
            "has",
            "had",
            "will",
            "would",
            "can",
            "could",
            "email",
            "message",
            "sent",
            "subject",
            "please",
            "thank",
            "thanks",
        }

        keywords = [word for word in words if len(word) >= min_length and word not in stop_words]

        return keywords[:10]  # Limit to top 10 keywords

    async def _load_patterns(self, user_id: UUID) -> list[dict]:
        """Load all learned patterns for a user.

        Args:
            user_id: User UUID

        Returns:
            List of pattern dictionaries from database
        """
        # This will be implemented in supabase_service.py
        return await self._supabase.fetch_label_patterns(user_id)
