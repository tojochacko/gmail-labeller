-- ============================================
-- Migration: Add email label tracking fields
-- ============================================
-- Description: Adds columns to track applied labels and sender information
-- Created: 2025-01-09
--
-- Execute this in your Supabase SQL Editor to add label tracking fields

-- Add label tracking columns to emails table
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS sender_email VARCHAR(255),
ADD COLUMN IF NOT EXISTS sender_domain VARCHAR(255),
ADD COLUMN IF NOT EXISTS applied_label VARCHAR(50),
ADD COLUMN IF NOT EXISTS label_applied_at TIMESTAMPTZ;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_emails_sender_domain ON emails(sender_domain);
CREATE INDEX IF NOT EXISTS idx_emails_applied_label ON emails(applied_label);
CREATE INDEX IF NOT EXISTS idx_emails_label_applied_at ON emails(label_applied_at DESC);

-- Add comments for documentation
COMMENT ON COLUMN emails.sender_email IS 'Email address of the sender';
COMMENT ON COLUMN emails.sender_domain IS 'Domain extracted from sender email (e.g., gmail.com)';
COMMENT ON COLUMN emails.applied_label IS 'User-applied label: Important or Not Important';
COMMENT ON COLUMN emails.label_applied_at IS 'Timestamp when label was applied';
