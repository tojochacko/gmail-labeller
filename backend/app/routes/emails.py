"""Email routes with auto-labeling support."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import get_email_service
from ..schemas.email import EmailItem, EmailListResponse, EmailListResponseWithStats, EmailStats
from ..services.email_service import EmailService

router = APIRouter()


@router.get(
    "",
    response_model=EmailListResponseWithStats,
    status_code=status.HTTP_200_OK,
)
async def list_emails(
    user_id: UUID = Query(..., description="Internal user identifier"),
    max_results: int = Query(20, ge=1, le=50),
    query: str | None = Query(
        None,
        description="Gmail search query (e.g., 'in:inbox', 'is:unread', or empty for all). Defaults to 'in:inbox'",
    ),
    category: Literal["important", "not_important", "uncategorized", "all"] | None = Query(
        None,
        description=(
            "Filter by label category: "
            "'important' (Important emails), "
            "'not_important' (Not Important emails), "
            "'uncategorized' (no label), "
            "'all' or omit for all emails"
        ),
    ),
    include_stats: bool = Query(
        True,
        description="Include categorization statistics in response",
    ),
    email_service: EmailService = Depends(get_email_service),
) -> EmailListResponseWithStats:
    """Fetch latest Gmail messages for the authenticated user.

    NEW (2025-11-09): Now supports category filtering and returns statistics!

    Features:
    - Auto-labeling: New emails are automatically categorized based on learned patterns
    - Category filtering: Filter by Important, Not Important, or Uncategorized
    - Statistics: Get counts of emails by category and labeling source
    - Confidence scores: See how confident the auto-labeling system is

    Returns:
        EmailListResponseWithStats with filtered emails and categorization statistics
    """
    try:
        # Fetch all emails (with auto-labeling applied during fetch)
        all_emails = await email_service.fetch_latest_emails(
            user_id=user_id, max_results=max_results, query=query
        )

        # Calculate statistics before filtering
        stats = _calculate_stats(all_emails)

        # Filter by category if requested
        if category and category != "all":
            filtered_emails = _filter_by_category(all_emails, category)
        else:
            filtered_emails = all_emails

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    return EmailListResponseWithStats(
        items=filtered_emails,
        stats=stats,
    )


def _filter_by_category(
    emails: list[EmailItem],
    category: Literal["important", "not_important", "uncategorized"],
) -> list[EmailItem]:
    """Filter emails by label category.

    Args:
        emails: List of all emails
        category: Category to filter by

    Returns:
        Filtered list of emails
    """
    if category == "important":
        return [e for e in emails if e.label == "Important"]
    elif category == "not_important":
        return [e for e in emails if e.label == "Not Important"]
    elif category == "uncategorized":
        return [e for e in emails if not e.label]
    else:
        return emails


def _calculate_stats(emails: list[EmailItem]) -> EmailStats:
    """Calculate categorization statistics.

    Args:
        emails: List of all emails

    Returns:
        EmailStats with counts
    """
    total = len(emails)
    important = sum(1 for e in emails if e.label == "Important")
    not_important = sum(1 for e in emails if e.label == "Not Important")
    uncategorized = sum(1 for e in emails if not e.label)

    # Count by labeling source (new schema)
    auto_labeled = sum(1 for e in emails if e.label_source == "auto")
    manual_labeled = sum(1 for e in emails if e.label_source == "manual")

    # Fallback to deprecated fields if new schema not populated yet
    if auto_labeled == 0 and manual_labeled == 0:
        manual_labeled = sum(1 for e in emails if e.applied_label)
        # agent_suggestion count (deprecated, but include for transition period)
        auto_labeled = sum(1 for e in emails if e.agent_suggestion and not e.applied_label)

    return EmailStats(
        total=total,
        important=important,
        not_important=not_important,
        uncategorized=uncategorized,
        auto_labeled=auto_labeled,
        manual_labeled=manual_labeled,
    )
