# Auto-Label Implementation Plan

## 🎯 **Vision**

Transform the Gmail Labeler from a suggestion-based system to an **intelligent auto-labeling system** that learns from user behavior and automatically categorizes emails during the fetch process.

---

## 📋 **Overview**

### **Current Flow (Suggestion-Based)**
```
Fetch Emails → Store in DB → User triggers agent → Agent suggests → User manually applies → Gmail labeled
```

### **New Flow (Auto-Label with Learning)**
```
Fetch Emails → Pattern matching → Auto-label → Store in DB + Gmail → Display 3 categories → User re-marks (optional) → Patterns updated
```

### **Three Email Categories**
1. **Important** - Auto-labeled as important based on patterns
2. **Not Important** - Auto-labeled as not important based on patterns
3. **Uncategorized** - Agent couldn't confidently decide (confidence < threshold)

---

## 🗄️ **Phase 1: Database Schema Changes**

### **1.1 Consolidate Columns in `emails` Table**

**Current Schema:**
```sql
emails:
  - agent_suggestion VARCHAR(50)     -- "Important" or "Not Important" (suggestion only)
  - applied_label VARCHAR(50)        -- "Important" or "Not Important" (user-applied)
  - label_applied_at TIMESTAMPTZ
```

**New Schema:**
```sql
emails:
  - label VARCHAR(50)                -- "Important", "Not Important", or NULL (uncategorized)
  - label_confidence DECIMAL(3,2)    -- 0.00 to 1.00 (pattern matching confidence)
  - label_source VARCHAR(20)         -- "auto", "manual", or "re_marked"
  - labeled_at TIMESTAMPTZ           -- When label was applied
  - last_updated_by VARCHAR(20)      -- "system" or "user"
```

**Migration SQL:**
```sql
-- Step 1: Add new columns
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS label VARCHAR(50),
ADD COLUMN IF NOT EXISTS label_confidence DECIMAL(3,2),
ADD COLUMN IF NOT EXISTS label_source VARCHAR(20),
ADD COLUMN IF NOT EXISTS labeled_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_updated_by VARCHAR(20);

-- Step 2: Migrate existing data
-- Priority: applied_label (user action) > agent_suggestion (AI suggestion)
UPDATE emails
SET
  label = COALESCE(applied_label, agent_suggestion),
  label_source = CASE
    WHEN applied_label IS NOT NULL THEN 'manual'
    WHEN agent_suggestion IS NOT NULL THEN 'auto'
    ELSE NULL
  END,
  labeled_at = COALESCE(label_applied_at, updated_at),
  last_updated_by = CASE
    WHEN applied_label IS NOT NULL THEN 'user'
    WHEN agent_suggestion IS NOT NULL THEN 'system'
    ELSE NULL
  END,
  label_confidence = CASE
    WHEN applied_label IS NOT NULL THEN 1.00  -- User actions = 100% confidence
    WHEN agent_suggestion IS NOT NULL THEN 0.75  -- AI suggestions = 75% confidence
    ELSE NULL
  END
WHERE agent_suggestion IS NOT NULL OR applied_label IS NOT NULL;

-- Step 3: Drop old columns (after verifying migration)
-- ALTER TABLE emails DROP COLUMN agent_suggestion;
-- ALTER TABLE emails DROP COLUMN applied_label;
-- ALTER TABLE emails DROP COLUMN label_applied_at;
```

### **1.2 Update Indexes**
```sql
-- Remove old indexes
DROP INDEX IF EXISTS idx_emails_applied_label;

-- Add new indexes
CREATE INDEX IF NOT EXISTS idx_emails_label ON emails(label);
CREATE INDEX IF NOT EXISTS idx_emails_label_source ON emails(label_source);
CREATE INDEX IF NOT EXISTS idx_emails_labeled_at ON emails(labeled_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_user_label ON emails(user_id, label, labeled_at DESC);
```

---

## 🧠 **Phase 2: Auto-Labeling Engine**

### **2.1 Pattern Matching Service**

**File**: `backend/app/services/auto_label_service.py` (NEW)

```python
class AutoLabelService:
    """Intelligent auto-labeling based on learned patterns."""

    def __init__(self, pattern_service: PatternLearningService):
        self._pattern_service = pattern_service

    async def auto_label_email(
        self,
        email: EmailItem,
        user_id: UUID
    ) -> tuple[str | None, float]:
        """
        Auto-label email based on learned patterns.

        Returns:
            tuple: (label, confidence) where label is "Important", "Not Important", or None
        """
        # Get learned patterns for this user
        context = await self._pattern_service.get_learned_context(user_id)

        # Extract email features
        sender_domain = email.sender_domain
        subject = email.subject or ""
        snippet = email.snippet or ""

        # Calculate importance scores
        important_score = 0.0
        not_important_score = 0.0

        # 1. Domain-based scoring (highest weight = 0.5)
        if sender_domain:
            if sender_domain in context.important_domains:
                important_score += 0.5
                logger.debug(f"Domain match: {sender_domain} → Important")
            elif sender_domain in context.not_important_domains:
                not_important_score += 0.5
                logger.debug(f"Domain match: {sender_domain} → Not Important")

        # 2. Keyword-based scoring (weight = 0.3)
        combined_text = f"{subject} {snippet}".lower()

        important_keyword_matches = sum(
            1 for keyword in context.important_keywords
            if keyword.lower() in combined_text
        )
        not_important_keyword_matches = sum(
            1 for keyword in context.not_important_keywords
            if keyword.lower() in combined_text
        )

        if important_keyword_matches > 0:
            important_score += min(0.3, important_keyword_matches * 0.1)
            logger.debug(f"Keyword matches: {important_keyword_matches} → Important")

        if not_important_keyword_matches > 0:
            not_important_score += min(0.3, not_important_keyword_matches * 0.1)
            logger.debug(f"Keyword matches: {not_important_keyword_matches} → Not Important")

        # 3. Subject pattern scoring (weight = 0.2)
        for pattern in context.important_subject_patterns:
            if pattern.lower() in subject.lower():
                important_score += 0.2
                logger.debug(f"Subject pattern match: {pattern} → Important")
                break

        for pattern in context.not_important_subject_patterns:
            if pattern.lower() in subject.lower():
                not_important_score += 0.2
                logger.debug(f"Subject pattern match: {pattern} → Not Important")
                break

        # Determine label based on scores
        confidence_threshold = 0.4  # Minimum confidence to auto-label

        if important_score > not_important_score and important_score >= confidence_threshold:
            label = "Important"
            confidence = min(important_score, 0.99)  # Cap at 99% for auto-labels
        elif not_important_score > important_score and not_important_score >= confidence_threshold:
            label = "Not Important"
            confidence = min(not_important_score, 0.99)
        else:
            # Uncertain - leave uncategorized
            label = None
            confidence = max(important_score, not_important_score)

        logger.info(
            f"Auto-label result: {label} (confidence={confidence:.2f}, "
            f"important_score={important_score:.2f}, not_important_score={not_important_score:.2f})"
        )

        return label, confidence
```

### **2.2 Configuration**
```python
# backend/app/config.py
class Settings(BaseSettings):
    # ... existing settings ...

    # Auto-labeling configuration
    auto_label_enabled: bool = Field(default=True, alias="AUTO_LABEL_ENABLED")
    auto_label_confidence_threshold: float = Field(default=0.4, alias="AUTO_LABEL_CONFIDENCE_THRESHOLD")
    auto_label_apply_to_gmail: bool = Field(default=True, alias="AUTO_LABEL_APPLY_TO_GMAIL")
```

---

## 🔄 **Phase 3: Update Email Fetch Flow**

### **3.1 Modified Email Service**

**File**: `backend/app/services/email_service.py`

```python
class EmailService:
    def __init__(
        self,
        gmail_service: GmailService,
        supabase: SupabaseService,
        auto_label_service: AutoLabelService,  # NEW
        label_service: LabelService,  # NEW
        settings: Settings,  # NEW
    ):
        self._gmail_service = gmail_service
        self._supabase = supabase
        self._auto_label_service = auto_label_service
        self._label_service = label_service
        self._settings = settings

    async def fetch_latest_emails(
        self, user_id: UUID, max_results: int = 20, query: str | None = None
    ) -> list[EmailItem]:
        """Fetch emails and auto-label based on learned patterns."""

        logger.info(f"Fetching emails for user {user_id}, auto_label={self._settings.auto_label_enabled}")

        tokens = await self._ensure_tokens(user_id)
        messages = await self._gmail_service.list_messages(
            tokens=tokens,
            user_id=str(user_id),
            max_results=max_results,
            query=query,
        )

        logger.info(f"Fetched {len(messages)} Gmail messages")

        items: list[EmailItem] = []
        for raw in messages:
            item = self._parse_email(raw)

            # Check if email already exists
            existing = await self._supabase.fetch_email_by_gmail_id(user_id, item.gmail_message_id)

            if existing:
                # Reuse existing ID and preserve user-applied labels
                item.id = existing.id

                # Preserve manual labels (don't override user decisions)
                if existing.label and existing.label_source in ('manual', 're_marked'):
                    item.label = existing.label
                    item.label_confidence = existing.label_confidence
                    item.label_source = existing.label_source
                    item.labeled_at = existing.labeled_at
                    item.last_updated_by = existing.last_updated_by
                    logger.debug(f"Preserved manual label '{existing.label}' for {item.id}")
                else:
                    # Re-evaluate auto-label (patterns may have improved)
                    await self._apply_auto_label(item, user_id, tokens)
            else:
                # New email - apply auto-label
                await self._apply_auto_label(item, user_id, tokens)

            await self._supabase.upsert_email(user_id, item)
            items.append(item)

        logger.info(f"Processed {len(items)} emails with auto-labeling")
        return items

    async def _apply_auto_label(
        self,
        item: EmailItem,
        user_id: UUID,
        tokens: GmailTokens
    ) -> None:
        """Apply auto-label to email using pattern matching."""

        if not self._settings.auto_label_enabled:
            logger.debug("Auto-labeling disabled in config")
            return

        # Get auto-label from pattern matching
        label, confidence = await self._auto_label_service.auto_label_email(item, user_id)

        if label:
            logger.info(
                f"Auto-labeling email {item.gmail_message_id} as '{label}' "
                f"(confidence={confidence:.2f})"
            )

            # Update EmailItem with auto-label
            item.label = label
            item.label_confidence = confidence
            item.label_source = "auto"
            item.labeled_at = datetime.now(timezone.utc)
            item.last_updated_by = "system"

            # Apply label to Gmail if configured
            if self._settings.auto_label_apply_to_gmail:
                try:
                    await self._label_service.apply_label_to_gmail_only(
                        user_id=user_id,
                        gmail_message_id=item.gmail_message_id,
                        label_name=label,
                        tokens=tokens,
                    )
                    logger.info(f"✅ Applied label '{label}' to Gmail")
                except Exception as e:
                    logger.error(f"Failed to apply label to Gmail: {e}")
                    # Continue - we'll still have the label in the database
        else:
            logger.debug(
                f"Email {item.gmail_message_id} uncategorized "
                f"(confidence={confidence:.2f} below threshold)"
            )
            item.label = None
            item.label_confidence = confidence
            item.label_source = None
```

---

## 🎨 **Phase 4: UI Changes**

### **4.1 Update Email Categories Display**

**File**: `electron-app/src/App.tsx`

```tsx
// Group emails by label (not agent_suggestion)
const importantEmails = emails.filter(
  (email) => email.label?.toLowerCase() === 'important'
)
const notImportantEmails = emails.filter(
  (email) => email.label?.toLowerCase() === 'not important'
)
const uncategorizedEmails = emails.filter((email) => !email.label)

return (
  <>
    {/* Important Section */}
    <section className='card'>
      <h2>🔴 Important Emails ({importantEmails.length})</h2>
      <p className='hint'>
        Auto-labeled as important based on learned patterns
      </p>
      <ul className='email-list'>
        {importantEmails.map((email) => (
          <li key={email.id} className='email-item'>
            <h3>{email.subject || '(no subject)'}</h3>
            <p className='email-meta'>
              From: {email.senderEmail || 'Unknown'} |
              Received {new Date(email.receivedAt).toLocaleString()}
            </p>
            {email.snippet && <p className='email-snippet'>{email.snippet}</p>}

            {/* Show confidence and source */}
            <p className='email-label-info'>
              {email.labelSource === 'auto' && (
                <span className='badge auto-label'>
                  Auto-labeled ({(email.labelConfidence * 100).toFixed(0)}% confidence)
                </span>
              )}
              {email.labelSource === 'manual' && (
                <span className='badge manual-label'>Manually labeled</span>
              )}
              {email.labelSource === 're_marked' && (
                <span className='badge re-marked-label'>Re-marked by you</span>
              )}
            </p>

            <div className='email-actions'>
              <button
                type='button'
                onClick={() => handleRemarkLabel(email, 'Not Important')}
              >
                Re-mark as Not Important
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>

    {/* Not Important Section */}
    <section className='card'>
      <h2>⚪ Not Important ({notImportantEmails.length})</h2>
      <p className='hint'>
        Auto-labeled as not important based on learned patterns
      </p>
      {/* Similar structure */}
    </section>

    {/* Uncategorized Section */}
    <section className='card'>
      <h2>❓ Uncategorized ({uncategorizedEmails.length})</h2>
      <p className='hint'>
        System couldn't confidently categorize these. Please label them to help improve accuracy.
      </p>
      <ul className='email-list'>
        {uncategorizedEmails.map((email) => (
          <li key={email.id} className='email-item'>
            {/* Show both action buttons */}
            <div className='email-actions'>
              <button onClick={() => handleApplyLabel(email, 'Important')}>
                Mark as Important
              </button>
              <button onClick={() => handleApplyLabel(email, 'Not Important')}>
                Mark as Not Important
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  </>
)
```

### **4.2 Handle Re-marking (Learning Feedback)**

```tsx
const handleRemarkLabel = useCallback(
  async (email: EmailItem, newLabel: string) => {
    if (!session) return

    setLabelStatuses((current) => ({
      ...current,
      [email.id]: `Re-marking as ${newLabel}...`
    }))

    try {
      // Call new re-mark endpoint (triggers pattern learning)
      await api.labels.remark({
        userId: session.userId,
        emailId: email.id,
        gmailMessageId: email.gmailMessageId,
        newLabel: newLabel,
        previousLabel: email.label,
      })

      setLabelStatuses((current) => ({
        ...current,
        [email.id]: `Re-marked as ${newLabel}`,
      }))

      // Refresh to show updated categorization
      setTimeout(() => {
        void handleFetchEmails()
      }, 1000)
    } catch (error) {
      console.error('Failed to re-mark email', error)
      setLabelStatuses((current) => ({
        ...current,
        [email.id]: 'Re-marking failed'
      }))
    }
  },
  [api, session, handleFetchEmails],
)
```

---

## 🔄 **Phase 5: Pattern Learning Updates**

### **5.1 New Re-mark Endpoint**

**File**: `backend/app/routes/labels.py`

```python
@router.post(
    "/remark",
    response_model=ApplyLabelResponse,
    status_code=status.HTTP_200_OK,
)
async def remark_label(
    payload: RemarkLabelRequest,  # NEW schema
    label_service: LabelService = Depends(get_label_service),
) -> ApplyLabelResponse:
    """
    Re-mark an email with a new label and update learning patterns.

    This endpoint:
    1. Updates the label in Gmail
    2. Updates the label in database
    3. Extracts and updates patterns for better future auto-labeling
    """
    try:
        return await label_service.remark_label(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

### **5.2 Re-mark Service Logic**

**File**: `backend/app/services/label_service.py`

```python
async def remark_label(self, request: RemarkLabelRequest) -> ApplyLabelResponse:
    """
    Re-mark email and update patterns for learning.

    This is different from apply_label because:
    1. It's a user correction of an auto-label
    2. It provides stronger learning signal (user override)
    3. It updates patterns with higher weight
    """
    logger.info(
        f"Re-marking email {request.email_id}: {request.previous_label} → {request.new_label}"
    )

    tokens = await self._ensure_tokens(request.user_id)

    # Ensure email exists
    email = await self._ensure_email_in_database(
        user_id=request.user_id,
        gmail_message_id=request.gmail_message_id,
        tokens=tokens,
    )

    if not email:
        raise ValueError(f"Email {request.gmail_message_id} not found")

    # Apply new label to Gmail
    await self._gmail_service.apply_label(
        message_id=request.gmail_message_id,
        label_id=request.new_label,
        tokens=tokens,
        user_id=str(request.user_id),
    )

    # Update database with re-marked label
    domain = self._extract_domain(email.sender_email) if email.sender_email else None

    await self._supabase.update_email_label_remark(
        email_id=email.id,
        new_label=request.new_label,
        label_confidence=1.0,  # User corrections = 100% confidence
        label_source="re_marked",
        sender_domain=domain,
    )

    # Extract patterns with HIGH weight (user correction is strong signal)
    await self._pattern_service.extract_and_store_patterns(
        request=PatternExtractionRequest(
            email_id=email.id,
            applied_label=request.new_label,
            sender_email=email.sender_email or "",
            email_subject=email.subject or "",
            email_snippet=email.snippet or "",
        ),
        user_id=request.user_id,
        weight_multiplier=2.0,  # Re-marks get 2x weight for faster learning
    )

    logger.info(
        f"✅ Re-marked email {email.id} as '{request.new_label}' and updated patterns"
    )

    return ApplyLabelResponse(success=True, applied_label=request.new_label)
```

---

## 📊 **Phase 6: Schema Updates**

### **6.1 Update EmailItem Model**

**File**: `backend/app/schemas/email.py`

```python
class EmailItem(BaseModel):
    """Email with consolidated label field."""

    id: UUID = Field(..., description="Internal UUID for Supabase record.")
    gmail_message_id: str = Field(..., description="Gmail message identifier.")
    thread_id: str = Field(..., description="Gmail thread identifier.")
    subject: str = Field(..., description="Email subject line.")
    snippet: Optional[str] = Field(default=None, description="Trimmed preview of the body.")
    sender_email: Optional[str] = Field(default=None, description="Email address of the sender.")
    sender_domain: Optional[str] = Field(
        default=None, description="Domain extracted from sender email."
    )
    received_at: datetime = Field(..., description="Timestamp from Gmail.")
    processed_at: Optional[datetime] = Field(
        default=None, description="Timestamp of the last processing run."
    )

    # CONSOLIDATED LABEL FIELDS (replaces agent_suggestion + applied_label)
    label: Optional[str] = Field(
        default=None,
        description="Current label: 'Important', 'Not Important', or None (uncategorized)."
    )
    label_confidence: Optional[float] = Field(
        default=None,
        description="Confidence score (0.0-1.0) for the label.",
        ge=0.0,
        le=1.0,
    )
    label_source: Optional[str] = Field(
        default=None,
        description="How the label was applied: 'auto', 'manual', or 're_marked'."
    )
    labeled_at: Optional[datetime] = Field(
        default=None, description="When the label was applied."
    )
    last_updated_by: Optional[str] = Field(
        default=None, description="Who last updated: 'system' or 'user'."
    )
```

### **6.2 New Request Schema**

**File**: `backend/app/schemas/labels.py`

```python
class RemarkLabelRequest(BaseModel):
    """Request to re-mark an email (user correction)."""

    user_id: UUID = Field(..., description="Internal user identifier.")
    email_id: UUID = Field(..., description="Internal email UUID.")
    gmail_message_id: str = Field(..., description="Gmail message ID.")
    previous_label: Optional[str] = Field(..., description="Previous label (for learning).")
    new_label: str = Field(..., description="New label to apply.")
```

---

## 🧪 **Phase 7: Testing Strategy**

### **7.1 Unit Tests**

```python
# tests/test_auto_label_service.py

async def test_auto_label_by_domain():
    """Test auto-labeling based on learned domain patterns."""
    # Given: User has marked emails from "important-domain.com" as Important
    # When: New email arrives from "important-domain.com"
    # Then: Should auto-label as Important with high confidence

async def test_auto_label_by_keywords():
    """Test auto-labeling based on subject/content keywords."""
    # Given: User has marked emails with "urgent" as Important
    # When: New email with subject "Urgent: Review needed"
    # Then: Should auto-label as Important

async def test_auto_label_uncategorized():
    """Test emails remain uncategorized when confidence is low."""
    # Given: No patterns match this email
    # When: New email from unknown sender with generic content
    # Then: Should remain uncategorized (label=None)

async def test_remark_updates_patterns():
    """Test re-marking updates pattern weights."""
    # Given: Email auto-labeled as "Not Important"
    # When: User re-marks as "Important"
    # Then: Pattern weights updated with 2x multiplier

async def test_preserve_manual_labels():
    """Test manual labels are not overridden by auto-label."""
    # Given: User manually labeled email as "Important"
    # When: Fetch emails again (re-sync)
    # Then: Manual label preserved, not re-evaluated
```

### **7.2 Integration Tests**

```python
# tests/integration/test_auto_label_flow.py

async def test_full_auto_label_flow():
    """Test complete auto-label workflow."""
    # 1. Fetch emails
    # 2. Verify auto-labels applied to database
    # 3. Verify auto-labels applied to Gmail
    # 4. Verify emails displayed in correct categories
    # 5. Re-mark an email
    # 6. Verify patterns updated
    # 7. Fetch new similar email
    # 8. Verify improved auto-labeling
```

---

## 📅 **Phase 8: Migration & Rollout**

### **8.1 Migration Steps**

**Step 1: Backup Database**
```bash
# Backup current database
pg_dump -h <supabase-host> -U postgres <database> > backup_before_auto_label.sql
```

**Step 2: Run Schema Migration**
```sql
-- Execute migration SQL from Phase 1.1
-- Migrate data from old columns to new consolidated columns
```

**Step 3: Deploy Backend Changes**
```bash
# Deploy with feature flag disabled initially
AUTO_LABEL_ENABLED=false
```

**Step 4: Verify Migration**
```sql
-- Verify data migration
SELECT
  COUNT(*) as total,
  COUNT(label) as labeled,
  COUNT(CASE WHEN label_source = 'manual' THEN 1 END) as manual_labels,
  COUNT(CASE WHEN label_source = 'auto' THEN 1 END) as auto_labels
FROM emails;
```

**Step 5: Enable Auto-Labeling**
```bash
# Gradually enable for testing
AUTO_LABEL_ENABLED=true
AUTO_LABEL_APPLY_TO_GMAIL=false  # Test database-only first
```

**Step 6: Full Rollout**
```bash
# Enable full auto-labeling including Gmail
AUTO_LABEL_ENABLED=true
AUTO_LABEL_APPLY_TO_GMAIL=true
```

### **8.2 Rollback Plan**

If issues occur:

```sql
-- Restore old columns from new ones
UPDATE emails
SET
  applied_label = CASE WHEN label_source IN ('manual', 're_marked') THEN label END,
  agent_suggestion = CASE WHEN label_source = 'auto' THEN label END,
  label_applied_at = labeled_at
WHERE label IS NOT NULL;
```

---

## 📈 **Phase 9: Monitoring & Metrics**

### **9.1 Key Metrics to Track**

```sql
-- Auto-labeling accuracy
SELECT
  label_source,
  AVG(label_confidence) as avg_confidence,
  COUNT(*) as count
FROM emails
WHERE label IS NOT NULL
GROUP BY label_source;

-- Re-mark rate (indicates auto-label accuracy)
SELECT
  COUNT(CASE WHEN label_source = 're_marked' THEN 1 END) * 100.0 / COUNT(*) as remark_percentage
FROM emails
WHERE label IS NOT NULL;

-- Category distribution
SELECT
  label,
  COUNT(*) as count,
  AVG(label_confidence) as avg_confidence
FROM emails
GROUP BY label
ORDER BY count DESC;
```

### **9.2 Logging**

Add comprehensive logging:
```python
logger.info(f"Auto-label stats: {important_count} Important, {not_important_count} Not Important, {uncategorized_count} Uncategorized")
logger.info(f"Average confidence: {avg_confidence:.2f}")
logger.info(f"Pattern match rate: {pattern_match_rate:.1f}%")
```

---

## 🎯 **Success Criteria**

### **Phase 1-3 (Core Auto-Labeling)**
- ✅ Database schema migrated successfully
- ✅ Auto-labeling engine running
- ✅ Emails auto-labeled during fetch
- ✅ Labels applied to Gmail automatically
- ✅ >60% of emails auto-labeled (not uncategorized)

### **Phase 4-5 (UI & Learning)**
- ✅ Three categories displayed correctly
- ✅ Re-marking updates patterns
- ✅ Manual labels preserved during re-fetch
- ✅ Pattern accuracy improves over time

### **Phase 6-9 (Quality & Reliability)**
- ✅ All tests passing
- ✅ <10% re-mark rate (high accuracy)
- ✅ Zero data loss during migration
- ✅ Performance: <2s for auto-labeling 20 emails

---

## ⏱️ **Estimated Timeline**

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Database Schema | 2 hours | None |
| Phase 2: Auto-Label Engine | 4 hours | Phase 1 |
| Phase 3: Email Fetch Flow | 3 hours | Phase 2 |
| Phase 4: UI Changes | 3 hours | Phase 3 |
| Phase 5: Pattern Learning | 2 hours | Phase 4 |
| Phase 6: Schema Updates | 1 hour | Phase 5 |
| Phase 7: Testing | 4 hours | Phase 6 |
| Phase 8: Migration | 2 hours | Phase 7 |
| Phase 9: Monitoring | 1 hour | Phase 8 |
| **Total** | **~22 hours** | |

---

## 🚀 **Implementation Order**

### **Sprint 1: Foundation (8 hours)**
1. Database schema changes (Phase 1)
2. Auto-label engine (Phase 2)
3. Update EmailItem schema (Phase 6.1)

### **Sprint 2: Integration (7 hours)**
1. Update email fetch flow (Phase 3)
2. UI changes (Phase 4)
3. Re-mark endpoint (Phase 5.1)

### **Sprint 3: Polish (7 hours)**
1. Pattern learning updates (Phase 5.2)
2. Comprehensive testing (Phase 7)
3. Migration & monitoring (Phase 8, 9)

---

## ❓ **Open Questions for Review**

1. **Confidence Threshold**: Should we use 0.4 (40%) as the minimum confidence for auto-labeling, or adjust?
2. **Gmail Application**: Should auto-labels be applied to Gmail immediately, or only after user confirmation?
3. **Re-evaluation**: Should we re-evaluate auto-labels when patterns improve, or only for new emails?
4. **Pattern Weights**: Should re-marks get 2x weight, or a different multiplier?
5. **Uncategorized Actions**: Should there be a "neutral" label option, or force binary Important/Not Important?
6. **Old Data**: Should we drop old columns immediately after migration, or keep for a grace period?

---

## 📝 **Next Steps**

After review and approval:
1. Address any questions/concerns
2. Adjust plan based on feedback
3. Create implementation tasks/tickets
4. Begin Sprint 1 implementation
5. Iterative testing and refinement

---

**Ready for review and feedback!** 🎉


Answer to Key questions:
1. **Confidence Threshold**: Use 0.4 (40%) as the minimum confidence for auto-labeling
2. **Gmail Application**: auto-labels be applied to Gmail immediately
3. **Re-evaluation**: evaluate auto-labels only for new emails
4. **Pattern Weights**: re-marks get 2x weight
5. **Uncategorized Actions**: Show in Uncategorized section for manual labeling
6. **Old Data**: drop old columns immediately after migration