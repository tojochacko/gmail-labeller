# Database Migration Execution Guide

## Issue: "column 'label' does not exist" Error

This error occurs when trying to run migration 002 before migration 001, or when statements aren't executed in the correct order.

---

## Quick Fix: Use the Safe Version

**Use**: `database/migrations/002_consolidate_label_schema_v2.sql`

This version breaks the migration into **6 safe sections** that you run **one at a time**.

---

## Step-by-Step Execution

### Prerequisites

1. Open **Supabase Dashboard** → **SQL Editor**
2. Create a **New Query**
3. Have file `002_consolidate_label_schema_v2.sql` open in another window

---

### Section 0: Pre-Migration Check ✅

**Purpose**: Verify migration 001 was executed

**Code**:
```sql
DO $$
DECLARE
    sender_email_exists BOOLEAN;
    applied_label_exists BOOLEAN;
BEGIN
    -- Check if columns from migration 001 exist
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'emails'
        AND column_name = 'sender_email'
    ) INTO sender_email_exists;

    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'emails'
        AND column_name = 'applied_label'
    ) INTO applied_label_exists;

    IF NOT sender_email_exists THEN
        RAISE EXCEPTION 'Migration 001 not executed! Column sender_email does not exist. Please run 001_add_email_label_fields.sql first.';
    END IF;

    IF NOT applied_label_exists THEN
        RAISE EXCEPTION 'Migration 001 not executed! Column applied_label does not exist. Please run 001_add_email_label_fields.sql first.';
    END IF;

    RAISE NOTICE '✅ Pre-migration check passed! Migration 001 columns exist.';
END $$;
```

**Expected Output**:
```
✅ Pre-migration check passed! Migration 001 columns exist.
```

**If Error**: "Migration 001 not executed!"
→ **Solution**: Run `database/migrations/001_add_email_label_fields.sql` first, then retry

---

### Section 1A: Add New Columns

**Purpose**: Add `label`, `label_confidence`, `label_source`, etc. to `emails` table

**Code**: Copy **SECTION 1A** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 1A complete: New columns added to emails table
```

**Verify**:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'emails'
AND column_name IN ('label', 'label_confidence', 'label_source', 'labeled_at', 'last_updated_by');
```
Should return **5 rows**.

---

### Section 1B: Add Constraints

**Purpose**: Add CHECK constraints and comments to new columns

**Code**: Copy **SECTION 1B** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 1B complete: Constraints added to emails table
```

---

### Section 2A: Migrate applied_label Data

**Purpose**: Migrate data from `applied_label` → `label` (manual labels)

**Code**: Copy **SECTION 2A** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 2A complete: Migrated X labels from applied_label
```

**Verify**:
```sql
SELECT COUNT(*) as manual_labels
FROM emails
WHERE label IS NOT NULL AND label_source = 'manual';
```

---

### Section 2B: Migrate agent_suggestion Data

**Purpose**: Migrate data from `agent_suggestion` → `label` (agent suggestions)

**Code**: Copy **SECTION 2B** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 2B complete: Migrated Y labels from agent_suggestion
```

**Verify**:
```sql
SELECT
  label,
  label_source,
  COUNT(*) as count
FROM emails
WHERE label IS NOT NULL
GROUP BY label, label_source;
```

---

### Section 3: Create Indexes on emails

**Purpose**: Add performance indexes for label queries

**Code**: Copy **SECTION 3** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 3 complete: Indexes created on emails table
```

---

### Section 4A: Add Columns to label_patterns

**Purpose**: Add learning tracking columns to `label_patterns` table

**Code**: Copy **SECTION 4A** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 4A complete: New columns added to label_patterns table
```

**Verify**:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'label_patterns'
AND column_name IN ('times_applied', 'times_corrected', 'last_applied_at', 'confidence_score', 'pattern_weight');
```
Should return **5 rows**.

---

### Section 4B: Add Constraints to label_patterns

**Purpose**: Add CHECK constraints to pattern tracking columns

**Code**: Copy **SECTION 4B** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 4B complete: Constraints added to label_patterns table
```

---

### Section 5: Create Indexes on label_patterns

**Purpose**: Add performance indexes for pattern queries

**Code**: Copy **SECTION 5** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
✅ Section 5 complete: Indexes created on label_patterns table
```

---

### Section 6: Final Verification 🎉

**Purpose**: Verify migration success and show summary

**Code**: Copy **SECTION 6** from `002_consolidate_label_schema_v2.sql`

**Expected Output**:
```
========================================
✅ MIGRATION 002 COMPLETE!
========================================
Emails with labels: X
Original label count: Y
Pattern count: Z
✅ All labels migrated successfully!
========================================
Next steps:
1. Restart your backend server
2. Test auto-labeling by fetching emails
3. After verification (1-2 days), drop old columns
========================================
```

---

## Post-Migration Steps

### 1. Restart Backend

```bash
# In devcontainer
cd /workspaces/autogen-test
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
```

### 2. Verify Auto-Labeling Works

**Check backend logs** for:
```
🔄 FETCH START: user=...
🆕 NEW EMAIL: ...
🤖 AUTO-LABELED: 'Important' (confidence: 0.652, matched: example.com)
✅ FETCH COMPLETE: 10 emails (5 new, 5 existing, 3 auto-labeled)
```

**Query database**:
```sql
-- View auto-labeled emails
SELECT
  gmail_message_id,
  subject,
  sender_email,
  label,
  label_confidence,
  label_source,
  labeled_at
FROM emails
WHERE label IS NOT NULL
ORDER BY labeled_at DESC
LIMIT 10;
```

### 3. Drop Old Columns (After 1-2 Days Verification)

⚠️ **ONLY run this after confirming auto-labeling works!**

```sql
-- This is irreversible!
ALTER TABLE emails
DROP COLUMN IF EXISTS agent_suggestion,
DROP COLUMN IF EXISTS applied_label,
DROP COLUMN IF EXISTS label_applied_at;

-- Verify old columns are gone
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'emails'
AND column_name IN ('agent_suggestion', 'applied_label', 'label_applied_at');
-- Should return 0 rows
```

---

## Troubleshooting

### Error: "Migration 001 not executed"

**Solution**: Run migration 001 first:

```bash
# In Supabase SQL Editor
# Copy and run: database/migrations/001_add_email_label_fields.sql
```

Then retry migration 002.

---

### Error: "column already exists"

**Cause**: Migration was partially run before

**Solution**: Skip to the section that hasn't been run yet, or run this cleanup:

```sql
-- Check which columns exist
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'emails'
AND column_name IN ('label', 'label_confidence', 'label_source', 'labeled_at', 'last_updated_by');

-- If all 5 exist, skip to Section 2A
-- If some exist, drop and retry:
ALTER TABLE emails
DROP COLUMN IF EXISTS label,
DROP COLUMN IF EXISTS label_confidence,
DROP COLUMN IF EXISTS label_source,
DROP COLUMN IF EXISTS labeled_at,
DROP COLUMN IF EXISTS last_updated_by;

-- Then start from Section 1A
```

---

### Error: "constraint already exists"

**Solution**: Continue to next section (constraints can be safely skipped if they exist)

---

### Verification Query Shows No Labels Migrated

**Check original data**:
```sql
SELECT
  COUNT(*) as total_emails,
  COUNT(applied_label) as with_applied_label,
  COUNT(agent_suggestion) as with_agent_suggestion
FROM emails;
```

If counts are 0, you don't have existing labels to migrate (this is OK - auto-labeling will create new ones).

---

## Summary: Safe Migration Steps

1. ✅ Run **Section 0** (Pre-check)
2. ✅ Run **Section 1A** (Add columns)
3. ✅ Run **Section 1B** (Add constraints)
4. ✅ Run **Section 2A** (Migrate applied_label)
5. ✅ Run **Section 2B** (Migrate agent_suggestion)
6. ✅ Run **Section 3** (Create indexes on emails)
7. ✅ Run **Section 4A** (Add pattern columns)
8. ✅ Run **Section 4B** (Add pattern constraints)
9. ✅ Run **Section 5** (Create indexes on patterns)
10. ✅ Run **Section 6** (Final verification)
11. 🚀 Restart backend
12. 🧪 Test auto-labeling
13. 🗑️ Drop old columns (after verification)

---

**Questions?** Check `AUTO_LABEL_IMPLEMENTATION_STATUS.md` for detailed documentation.
