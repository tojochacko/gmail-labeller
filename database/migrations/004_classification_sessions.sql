-- Migration 004: Classification sessions as task queue wrapper
--
-- The `emails` table becomes the task queue when scoped by session_id.
-- label_patterns is NEVER deleted (it stores learned knowledge).

-- New table: classification session (the "task queue" wrapper)
CREATE TABLE classification_sessions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status       VARCHAR(50) NOT NULL DEFAULT 'pending',
  -- status: pending | classifying | awaiting_review | completed | cleaned_up
  email_count  INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT valid_session_status CHECK (
    status IN ('pending', 'classifying', 'awaiting_review', 'completed', 'cleaned_up')
  )
);

-- Link emails to a session (makes emails the "queue items")
ALTER TABLE emails ADD COLUMN IF NOT EXISTS session_id UUID
  REFERENCES classification_sessions(id) ON DELETE SET NULL;

-- Group agent runs by batch for observability
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS batch_run_id UUID
  REFERENCES classification_sessions(id) ON DELETE SET NULL;

-- Index for fast queue queries
CREATE INDEX IF NOT EXISTS idx_emails_session_id ON emails(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_batch_run_id ON agent_runs(batch_run_id);
