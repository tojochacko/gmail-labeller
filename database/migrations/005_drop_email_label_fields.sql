-- Migration: Remove label fields from emails table
-- Gmail is the single source of truth for labels.
-- Labels are applied directly to Gmail and read from there;
-- they are no longer staged in the database.

ALTER TABLE emails
    DROP COLUMN IF EXISTS label,
    DROP COLUMN IF EXISTS label_confidence,
    DROP COLUMN IF EXISTS label_source,
    DROP COLUMN IF EXISTS labeled_at,
    DROP COLUMN IF EXISTS last_updated_by;

-- Drop the index that was created for the label column
DROP INDEX IF EXISTS idx_emails_label;
DROP INDEX IF EXISTS idx_emails_label_source;
