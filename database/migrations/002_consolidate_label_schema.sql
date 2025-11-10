-- ============================================
-- Migration: Consolidate Label Schema for Auto-Labeling
-- ============================================
-- Description: Consolidates agent_suggestion and applied_label into single
--              label field with metadata for auto-labeling system
-- Created: 2025-11-09
-- Dependencies: 001_add_email_label_fields.sql
--
-- Execute this in your Supabase SQL Editor

-- ============================================
-- STEP 1: Add new consolidated columns to emails table
-- ============================================

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS label VARCHAR(50),
ADD COLUMN IF NOT EXISTS label_confidence NUMERIC(3,2) CHECK (label_confidence >= 0 AND label_confidence <= 1),
ADD COLUMN IF NOT EXISTS label_source VARCHAR(20) CHECK (label_source IN ('auto', 'manual', 'agent')),
ADD COLUMN IF NOT EXISTS labeled_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_updated_by VARCHAR(20) CHECK (last_updated_by IN ('auto', 'user', 'agent'));

-- Add comments for documentation
COMMENT ON COLUMN emails.label IS 'Consolidated label: Important, Not Important, or NULL for Uncategorized';
COMMENT ON COLUMN emails.label_confidence IS 'Confidence score (0.0-1.0) for auto-applied labels';
COMMENT ON COLUMN emails.label_source IS 'Source of label: auto (pattern-based), manual (user), or agent (AI suggestion)';
COMMENT ON COLUMN emails.labeled_at IS 'Timestamp when label was applied or last updated';
COMMENT ON COLUMN emails.last_updated_by IS 'Last entity that updated the label: auto, user, or agent';

-- ============================================
-- STEP 2: Migrate existing data to new columns
-- ============================================

-- Migrate from applied_label (user-applied labels take precedence)
UPDATE emails
SET
    label = applied_label,
    label_confidence = 1.0,  -- Manual labels have 100% confidence
    label_source = 'manual',
    labeled_at = label_applied_at,
    last_updated_by = 'user'
WHERE applied_label IS NOT NULL;

-- Migrate from agent_suggestion (only if no manual label exists)
UPDATE emails
SET
    label = agent_suggestion,
    label_confidence = 0.5,  -- Agent suggestions get medium confidence
    label_source = 'agent',
    labeled_at = processed_at,
    last_updated_by = 'agent'
WHERE agent_suggestion IS NOT NULL
AND applied_label IS NULL;

-- ============================================
-- STEP 3: Create indexes for performance
-- ============================================

CREATE INDEX IF NOT EXISTS idx_emails_label ON emails(label) WHERE label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_emails_label_source ON emails(label_source);
CREATE INDEX IF NOT EXISTS idx_emails_label_confidence ON emails(label_confidence DESC);
CREATE INDEX IF NOT EXISTS idx_emails_labeled_at ON emails(labeled_at DESC);

-- Composite index for filtering by label and confidence
CREATE INDEX IF NOT EXISTS idx_emails_label_confidence_composite
ON emails(label, label_confidence DESC)
WHERE label IS NOT NULL;

-- ============================================
-- STEP 4: Add learning tracking to label_patterns table
-- ============================================

ALTER TABLE label_patterns
ADD COLUMN IF NOT EXISTS times_applied INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS times_corrected INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_applied_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(3,2) DEFAULT 0.50 CHECK (confidence_score >= 0 AND confidence_score <= 1),
ADD COLUMN IF NOT EXISTS pattern_weight NUMERIC(3,2) DEFAULT 1.0 CHECK (pattern_weight >= 0 AND pattern_weight <= 5);

-- Add comments
COMMENT ON COLUMN label_patterns.times_applied IS 'Number of times this pattern was used for auto-labeling';
COMMENT ON COLUMN label_patterns.times_corrected IS 'Number of times user corrected this pattern (re-marked)';
COMMENT ON COLUMN label_patterns.last_applied_at IS 'Last time this pattern was used for labeling';
COMMENT ON COLUMN label_patterns.confidence_score IS 'Pattern confidence based on success rate';
COMMENT ON COLUMN label_patterns.pattern_weight IS 'Weight multiplier (1.0 default, 2.0 for re-marks)';

-- Create indexes for pattern learning queries
CREATE INDEX IF NOT EXISTS idx_label_patterns_confidence ON label_patterns(confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_label_patterns_weight ON label_patterns(pattern_weight DESC);
CREATE INDEX IF NOT EXISTS idx_label_patterns_label ON label_patterns(label);
CREATE INDEX IF NOT EXISTS idx_label_patterns_last_applied ON label_patterns(last_applied_at DESC);

-- Composite index for finding high-confidence patterns
CREATE INDEX IF NOT EXISTS idx_label_patterns_label_confidence
ON label_patterns(label, confidence_score DESC, pattern_weight DESC);

-- ============================================
-- STEP 5: Verify migration success
-- ============================================

-- Check that data was migrated correctly
DO $$
DECLARE
    migrated_count INTEGER;
    original_count INTEGER;
BEGIN
    -- Count migrated labels
    SELECT COUNT(*) INTO migrated_count
    FROM emails
    WHERE label IS NOT NULL;

    -- Count original labels
    SELECT COUNT(*) INTO original_count
    FROM emails
    WHERE applied_label IS NOT NULL OR agent_suggestion IS NOT NULL;

    RAISE NOTICE 'Migration verification: % original labels, % migrated labels',
        original_count, migrated_count;

    IF migrated_count < original_count THEN
        RAISE WARNING 'Some labels may not have been migrated! Check data integrity.';
    ELSE
        RAISE NOTICE 'Migration successful! All labels migrated.';
    END IF;
END $$;

-- ============================================
-- STEP 6: Drop old columns (ONLY AFTER VERIFICATION)
-- ============================================
-- CAUTION: This is irreversible! Ensure migration was successful first.
-- Run this separately after verifying the migration worked:

-- ALTER TABLE emails
-- DROP COLUMN IF EXISTS agent_suggestion,
-- DROP COLUMN IF EXISTS applied_label,
-- DROP COLUMN IF EXISTS label_applied_at;

-- UNCOMMENT THE ABOVE AFTER VERIFYING MIGRATION SUCCESS

-- ============================================
-- ROLLBACK PROCEDURE (if needed)
-- ============================================
-- If you need to rollback this migration:
--
-- 1. Restore old columns from new ones:
--    UPDATE emails SET applied_label = label, label_applied_at = labeled_at WHERE label_source = 'manual';
--    UPDATE emails SET agent_suggestion = label WHERE label_source = 'agent';
--
-- 2. Drop new columns:
--    ALTER TABLE emails DROP COLUMN label, DROP COLUMN label_confidence,
--                       DROP COLUMN label_source, DROP COLUMN labeled_at,
--                       DROP COLUMN last_updated_by;
--
-- 3. Drop new pattern columns:
--    ALTER TABLE label_patterns DROP COLUMN times_applied, DROP COLUMN times_corrected,
--                                DROP COLUMN last_applied_at, DROP COLUMN confidence_score,
--                                DROP COLUMN pattern_weight;
