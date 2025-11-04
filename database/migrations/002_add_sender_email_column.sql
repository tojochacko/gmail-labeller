-- ============================================
-- Add sender_email column to emails table
-- ============================================
-- This migration adds the sender_email field for pattern learning

ALTER TABLE emails ADD COLUMN IF NOT EXISTS sender_email VARCHAR(255);

COMMENT ON COLUMN emails.sender_email IS 'Email address of the sender (From header)';

-- Index for sender email lookups
CREATE INDEX IF NOT EXISTS idx_emails_sender_email ON emails(sender_email);
