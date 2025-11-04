-- ============================================
-- AI Learning Feature - Label Patterns Migration
-- ============================================
-- This migration adds pattern learning capabilities to the Gmail Labeler
-- Run this in your Supabase SQL Editor after the base schema

-- ============================================
-- Label Patterns Table (AI Learning)
-- ============================================
CREATE TABLE IF NOT EXISTS label_patterns (
  pattern_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label_type VARCHAR(50) NOT NULL,
  pattern_type VARCHAR(50) NOT NULL,
  pattern_value TEXT NOT NULL,
  confidence_score DECIMAL(3,2) DEFAULT 1.0,
  occurrence_count INTEGER DEFAULT 1,
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  is_user_defined BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT valid_label_type CHECK (label_type IN ('Important', 'Not Important')),
  CONSTRAINT valid_pattern_type CHECK (pattern_type IN ('domain', 'keyword')),
  CONSTRAINT valid_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
  CONSTRAINT unique_user_pattern UNIQUE(user_id, label_type, pattern_type, pattern_value)
);

COMMENT ON TABLE label_patterns IS 'Learned patterns from email labeling for AI improvement';
COMMENT ON COLUMN label_patterns.label_type IS 'Label category: Important or Not Important';
COMMENT ON COLUMN label_patterns.pattern_type IS 'Type of pattern: domain or keyword';
COMMENT ON COLUMN label_patterns.pattern_value IS 'The actual domain or keyword value';
COMMENT ON COLUMN label_patterns.confidence_score IS 'Confidence score 0.0-1.0, increases with occurrences';
COMMENT ON COLUMN label_patterns.occurrence_count IS 'Number of times this pattern appeared';
COMMENT ON COLUMN label_patterns.is_user_defined IS 'True if manually added/edited by user';

-- ============================================
-- Indexes for Label Patterns
-- ============================================
CREATE INDEX IF NOT EXISTS idx_label_patterns_user_id ON label_patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_label_patterns_label_type ON label_patterns(label_type);
CREATE INDEX IF NOT EXISTS idx_label_patterns_pattern_type ON label_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_label_patterns_confidence ON label_patterns(confidence_score DESC);

-- ============================================
-- Row Level Security for Label Patterns
-- ============================================
ALTER TABLE label_patterns ENABLE ROW LEVEL SECURITY;

CREATE POLICY label_patterns_policy ON label_patterns
  FOR ALL
  USING (user_id = auth.uid());

-- ============================================
-- Updated_at trigger for Label Patterns
-- ============================================
CREATE TRIGGER update_label_patterns_updated_at
  BEFORE UPDATE ON label_patterns
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Add columns to emails table
-- ============================================
-- Add columns to track applied labels
ALTER TABLE emails ADD COLUMN IF NOT EXISTS applied_label VARCHAR(50);
ALTER TABLE emails ADD COLUMN IF NOT EXISTS label_applied_at TIMESTAMPTZ;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS sender_domain VARCHAR(255);

COMMENT ON COLUMN emails.applied_label IS 'Label actually applied by user';
COMMENT ON COLUMN emails.label_applied_at IS 'Timestamp when label was applied';
COMMENT ON COLUMN emails.sender_domain IS 'Extracted sender domain for pattern learning';

-- ============================================
-- Indexes for email pattern analysis
-- ============================================
CREATE INDEX IF NOT EXISTS idx_emails_applied_label ON emails(applied_label);
CREATE INDEX IF NOT EXISTS idx_emails_sender_domain ON emails(sender_domain);
