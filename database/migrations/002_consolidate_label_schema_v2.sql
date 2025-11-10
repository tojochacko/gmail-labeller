-- ============================================
-- Migration 002 v2: Consolidate Label Schema (SAFE VERSION)
-- ============================================
-- Description: Step-by-step migration with verification checks
-- Created: 2025-11-09
-- Dependencies: 001_add_email_label_fields.sql MUST be run first
--
-- IMPORTANT: Run each section separately in Supabase SQL Editor
-- Wait for success confirmation before proceeding to next section

-- ============================================
-- SECTION 0: Pre-Migration Verification
-- ============================================
-- Run this first to verify migration 001 was executed

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

-- ============================================
-- SECTION 1A: Add New Columns to emails Table
-- ============================================
-- Run this section and wait for success

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS label VARCHAR(50);

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS label_confidence NUMERIC(3,2);

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS label_source VARCHAR(20);

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS labeled_at TIMESTAMPTZ;

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS last_updated_by VARCHAR(20);

-- Verify columns were created
DO $$
BEGIN
    RAISE NOTICE '✅ Section 1A complete: New columns added to emails table';
END $$;

-- ============================================
-- SECTION 1B: Add Constraints to emails Table
-- ============================================
-- Run this section after 1A succeeds

ALTER TABLE emails
ADD CONSTRAINT check_label_confidence CHECK (label_confidence IS NULL OR (label_confidence >= 0 AND label_confidence <= 1));

ALTER TABLE emails
ADD CONSTRAINT check_label_source CHECK (label_source IS NULL OR label_source IN ('auto', 'manual', 'agent'));

ALTER TABLE emails
ADD CONSTRAINT check_last_updated_by CHECK (last_updated_by IS NULL OR last_updated_by IN ('auto', 'user', 'agent'));

-- Add comments
COMMENT ON COLUMN emails.label IS 'Consolidated label: Important, Not Important, or NULL for Uncategorized';
COMMENT ON COLUMN emails.label_confidence IS 'Confidence score (0.0-1.0) for auto-applied labels';
COMMENT ON COLUMN emails.label_source IS 'Source of label: auto (pattern-based), manual (user), or agent (AI suggestion)';
COMMENT ON COLUMN emails.labeled_at IS 'Timestamp when label was applied or last updated';
COMMENT ON COLUMN emails.last_updated_by IS 'Last entity that updated the label: auto, user, or agent';

-- Verify constraints were added
DO $$
BEGIN
    RAISE NOTICE '✅ Section 1B complete: Constraints added to emails table';
END $$;

-- ============================================
-- SECTION 2A: Migrate Data from applied_label
-- ============================================
-- Run this section after 1B succeeds

-- Migrate from applied_label (user-applied labels take precedence)
UPDATE emails
SET
    label = applied_label,
    label_confidence = 1.0,
    label_source = 'manual',
    labeled_at = label_applied_at,
    last_updated_by = 'user'
WHERE applied_label IS NOT NULL;

-- Check migration progress
DO $$
DECLARE
    migrated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO migrated_count
    FROM emails
    WHERE label IS NOT NULL AND label_source = 'manual';

    RAISE NOTICE '✅ Section 2A complete: Migrated % labels from applied_label', migrated_count;
END $$;

-- ============================================
-- SECTION 2B: Migrate Data from agent_suggestion
-- ============================================
-- Run this section after 2A succeeds

-- Migrate from agent_suggestion (only if no manual label exists)
UPDATE emails
SET
    label = agent_suggestion,
    label_confidence = 0.5,
    label_source = 'agent',
    labeled_at = processed_at,
    last_updated_by = 'agent'
WHERE agent_suggestion IS NOT NULL
AND applied_label IS NULL;

-- Check migration progress
DO $$
DECLARE
    agent_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO agent_count
    FROM emails
    WHERE label IS NOT NULL AND label_source = 'agent';

    RAISE NOTICE '✅ Section 2B complete: Migrated % labels from agent_suggestion', agent_count;
END $$;

-- ============================================
-- SECTION 3: Create Indexes on emails Table
-- ============================================
-- Run this section after 2B succeeds

CREATE INDEX IF NOT EXISTS idx_emails_label ON emails(label) WHERE label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_emails_label_source ON emails(label_source);
CREATE INDEX IF NOT EXISTS idx_emails_label_confidence ON emails(label_confidence DESC);
CREATE INDEX IF NOT EXISTS idx_emails_labeled_at ON emails(labeled_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_label_confidence_composite ON emails(label, label_confidence DESC) WHERE label IS NOT NULL;

-- Verify indexes were created
DO $$
BEGIN
    RAISE NOTICE '✅ Section 3 complete: Indexes created on emails table';
END $$;

-- ============================================
-- SECTION 4A: Add New Columns to label_patterns Table
-- ============================================
-- Run this section after Section 3 succeeds

ALTER TABLE label_patterns
ADD COLUMN IF NOT EXISTS times_applied INTEGER DEFAULT 0;

ALTER TABLE label_patterns
ADD COLUMN IF NOT EXISTS times_corrected INTEGER DEFAULT 0;

ALTER TABLE label_patterns
ADD COLUMN IF NOT EXISTS last_applied_at TIMESTAMPTZ;

ALTER TABLE label_patterns
ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(3,2) DEFAULT 0.50;

ALTER TABLE label_patterns
ADD COLUMN IF NOT EXISTS pattern_weight NUMERIC(3,2) DEFAULT 1.0;

-- Verify columns were created
DO $$
BEGIN
    RAISE NOTICE '✅ Section 4A complete: New columns added to label_patterns table';
END $$;

-- ============================================
-- SECTION 4B: Add Constraints to label_patterns Table
-- ============================================
-- Run this section after 4A succeeds

ALTER TABLE label_patterns
ADD CONSTRAINT check_confidence_score CHECK (confidence_score >= 0 AND confidence_score <= 1);

ALTER TABLE label_patterns
ADD CONSTRAINT check_pattern_weight CHECK (pattern_weight >= 0 AND pattern_weight <= 5);

-- Add comments
COMMENT ON COLUMN label_patterns.times_applied IS 'Number of times this pattern was used for auto-labeling';
COMMENT ON COLUMN label_patterns.times_corrected IS 'Number of times user corrected this pattern (re-marked)';
COMMENT ON COLUMN label_patterns.last_applied_at IS 'Last time this pattern was used for labeling';
COMMENT ON COLUMN label_patterns.confidence_score IS 'Pattern confidence based on success rate';
COMMENT ON COLUMN label_patterns.pattern_weight IS 'Weight multiplier (1.0 default, 2.0 for re-marks)';

-- Verify constraints were added
DO $$
BEGIN
    RAISE NOTICE '✅ Section 4B complete: Constraints added to label_patterns table';
END $$;

-- ============================================
-- SECTION 5: Create Indexes on label_patterns Table
-- ============================================
-- Run this section after 4B succeeds

CREATE INDEX IF NOT EXISTS idx_label_patterns_confidence ON label_patterns(confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_label_patterns_weight ON label_patterns(pattern_weight DESC);
CREATE INDEX IF NOT EXISTS idx_label_patterns_label ON label_patterns(label_type);
CREATE INDEX IF NOT EXISTS idx_label_patterns_last_applied ON label_patterns(last_applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_label_patterns_label_confidence ON label_patterns(label_type, confidence_score DESC, pattern_weight DESC);

-- Verify indexes were created
DO $$
BEGIN
    RAISE NOTICE '✅ Section 5 complete: Indexes created on label_patterns table';
END $$;

-- ============================================
-- SECTION 6: Final Verification
-- ============================================
-- Run this section last to verify migration success

DO $$
DECLARE
    emails_label_count INTEGER;
    original_count INTEGER;
    patterns_count INTEGER;
BEGIN
    -- Count migrated labels in emails table
    SELECT COUNT(*) INTO emails_label_count
    FROM emails
    WHERE label IS NOT NULL;

    -- Count original labels (applied_label + agent_suggestion)
    SELECT COUNT(*) INTO original_count
    FROM emails
    WHERE applied_label IS NOT NULL OR agent_suggestion IS NOT NULL;

    -- Count patterns
    SELECT COUNT(*) INTO patterns_count
    FROM label_patterns;

    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ MIGRATION 002 COMPLETE!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Emails with labels: %', emails_label_count;
    RAISE NOTICE 'Original label count: %', original_count;
    RAISE NOTICE 'Pattern count: %', patterns_count;

    IF emails_label_count < original_count THEN
        RAISE WARNING '⚠️  Some labels may not have been migrated! Check data integrity.';
    ELSE
        RAISE NOTICE '✅ All labels migrated successfully!';
    END IF;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Restart your backend server';
    RAISE NOTICE '2. Test auto-labeling by fetching emails';
    RAISE NOTICE '3. After verification (1-2 days), drop old columns:';
    RAISE NOTICE '   See migration file for DROP COLUMN statements';
    RAISE NOTICE '========================================';
END $$;
