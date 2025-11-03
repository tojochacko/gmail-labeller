-- ============================================
-- Gmail Labeler Database Schema
-- ============================================
-- This schema should be executed in your Supabase SQL Editor
-- to create all required tables for the Gmail Labeler backend.

-- ============================================
-- Users table
-- ============================================
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE users IS 'User accounts for Gmail Labeler';
COMMENT ON COLUMN users.email IS 'User email address (must match Google account)';

-- ============================================
-- Gmail tokens table
-- ============================================
CREATE TABLE IF NOT EXISTS gmail_tokens (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  scope TEXT NOT NULL,
  token_type VARCHAR(50) DEFAULT 'Bearer',
  id_token TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE gmail_tokens IS 'Encrypted OAuth tokens for Gmail access';
COMMENT ON COLUMN gmail_tokens.access_token IS 'Encrypted access token';
COMMENT ON COLUMN gmail_tokens.refresh_token IS 'Encrypted refresh token';

-- ============================================
-- Emails table
-- ============================================
CREATE TABLE IF NOT EXISTS emails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  gmail_message_id VARCHAR(255) NOT NULL,
  thread_id VARCHAR(255),
  subject TEXT,
  snippet TEXT,
  received_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ,
  agent_suggestion TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, gmail_message_id)
);

COMMENT ON TABLE emails IS 'Email metadata from Gmail';
COMMENT ON COLUMN emails.gmail_message_id IS 'Gmail message ID (not thread ID)';
COMMENT ON COLUMN emails.agent_suggestion IS 'AI-generated label suggestion';

-- ============================================
-- Agent runs table
-- ============================================
CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
  status VARCHAR(50) NOT NULL DEFAULT 'queued',
  result_payload JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_status CHECK (status IN ('queued', 'running', 'completed', 'failed'))
);

COMMENT ON TABLE agent_runs IS 'Agent execution history and results';
COMMENT ON COLUMN agent_runs.status IS 'Current status: queued, running, completed, failed';
COMMENT ON COLUMN agent_runs.result_payload IS 'JSON result from agent execution';

-- ============================================
-- Indexes for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_emails_user_id ON emails(user_id);
CREATE INDEX IF NOT EXISTS idx_emails_gmail_message_id ON emails(gmail_message_id);
CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_email_id ON agent_runs(email_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at DESC);

-- ============================================
-- Row Level Security (RLS) Policies
-- ============================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE gmail_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

-- Users can only see their own data
CREATE POLICY users_policy ON users
  FOR ALL
  USING (id = auth.uid());

CREATE POLICY gmail_tokens_policy ON gmail_tokens
  FOR ALL
  USING (user_id = auth.uid());

CREATE POLICY emails_policy ON emails
  FOR ALL
  USING (user_id = auth.uid());

CREATE POLICY agent_runs_policy ON agent_runs
  FOR ALL
  USING (user_id = auth.uid());

-- ============================================
-- Updated_at trigger function
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables
CREATE TRIGGER update_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_gmail_tokens_updated_at
  BEFORE UPDATE ON gmail_tokens
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_emails_updated_at
  BEFORE UPDATE ON emails
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agent_runs_updated_at
  BEFORE UPDATE ON agent_runs
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
