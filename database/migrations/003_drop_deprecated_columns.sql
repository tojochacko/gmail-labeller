-- ============================================
-- Migration 003: Drop Deprecated Label Columns
-- ============================================
-- Description: Drop old label columns after migration to consolidated schema
-- Created: 2025-11-10
-- Depends on: 002_consolidate_label_schema_v2.sql
--
-- IMPORTANT: Only run this after verifying all code changes work correctly!
-- ============================================

BEGIN;

-- Drop indexes on deprecated columns first
DROP INDEX IF EXISTS idx_emails_applied_label;

-- Drop deprecated columns
ALTER TABLE emails
DROP COLUMN IF EXISTS agent_suggestion,
DROP COLUMN IF EXISTS applied_label,
DROP COLUMN IF EXISTS label_applied_at;

-- Verify columns are dropped
DO $$
DECLARE
    agent_suggestion_exists BOOLEAN;
    applied_label_exists BOOLEAN;
    label_applied_at_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'emails' AND column_name = 'agent_suggestion'
    ) INTO agent_suggestion_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'emails' AND column_name = 'applied_label'
    ) INTO applied_label_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'emails' AND column_name = 'label_applied_at'
    ) INTO label_applied_at_exists;

    IF agent_suggestion_exists OR applied_label_exists OR label_applied_at_exists THEN
        RAISE EXCEPTION 'Failed to drop deprecated columns!';
    END IF;

    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ MIGRATION 003 COMPLETE!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'All deprecated columns successfully dropped:';
    RAISE NOTICE '  - agent_suggestion';
    RAISE NOTICE '  - applied_label';
    RAISE NOTICE '  - label_applied_at';
    RAISE NOTICE '';
    RAISE NOTICE 'Active label schema:';
    RAISE NOTICE '  - label (VARCHAR)';
    RAISE NOTICE '  - label_confidence (FLOAT)';
    RAISE NOTICE '  - label_source (VARCHAR)';
    RAISE NOTICE '  - labeled_at (TIMESTAMPTZ)';
    RAISE NOTICE '  - last_updated_by (VARCHAR)';
    RAISE NOTICE '========================================';
END $$;

COMMIT;
