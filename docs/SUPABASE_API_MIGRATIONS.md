# Supabase Schema Management via API

This project skips the Supabase CLI. Use either the hosted SQL editor or direct API calls to manage schema changes.

## Baseline Schema SQL
Run the following SQL block (all statements are idempotent) in the Supabase SQL editor or via the REST API to create tables, indexes, and RLS policies:

```sql
-- Extensions (UUID + crypto helpers)
create extension if not exists "pgcrypto";

-- Users table
create table if not exists public.users (
  id uuid primary key,
  email text not null unique,
  created_at timestamptz not null default now()
);

-- Gmail OAuth tokens
create table if not exists public.gmail_tokens (
  user_id uuid primary key references public.users(id) on delete cascade,
  access_token text not null,
  refresh_token text not null,
  expires_at timestamptz not null,
  scope text,
  token_type text not null default 'Bearer',
  id_token text,
  created_at timestamptz not null default now()
);

-- Email cache
create table if not exists public.emails (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  gmail_message_id text not null,
  thread_id text,
  subject text,
  snippet text,
  received_at timestamptz not null,
  processed_at timestamptz,
  agent_suggestion text,
  created_at timestamptz not null default now(),
  unique (user_id, gmail_message_id)
);
create index if not exists emails_user_id_idx on public.emails(user_id);
create index if not exists emails_received_at_idx on public.emails(user_id, received_at desc);

-- Label configuration cache
create table if not exists public.label_configs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  label_name text not null,
  description text,
  gmail_label_id text,
  created_at timestamptz not null default now(),
  unique (user_id, label_name)
);

-- Agent run log
create table if not exists public.agent_runs (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  email_id uuid not null references public.emails(id) on delete cascade,
  status text not null,
  result_payload jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists agent_runs_user_idx on public.agent_runs(user_id);

-- Row Level Security
alter table public.users enable row level security;
alter table public.gmail_tokens enable row level security;
alter table public.emails enable row level security;
alter table public.label_configs enable row level security;
alter table public.agent_runs enable row level security;

-- Helper function to read auth UID (works with auth and service role keys)
create or replace function public.current_user_id() returns uuid as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$ language sql stable;

-- Policies (allow service role + owner access)
drop policy if exists "service role access users" on public.users;
create policy "service role access users" on public.users
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists "user access to own row" on public.users;
create policy "user access to own row" on public.users
  for all using (id = public.current_user_id()) with check (id = public.current_user_id());

drop policy if exists "service role access gmail tokens" on public.gmail_tokens;
create policy "service role access gmail tokens" on public.gmail_tokens
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists "user access gmail tokens" on public.gmail_tokens;
create policy "user access gmail tokens" on public.gmail_tokens
  for select using (user_id = public.current_user_id());

drop policy if exists "service role access emails" on public.emails;
create policy "service role access emails" on public.emails
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists "user access emails" on public.emails;
create policy "user access emails" on public.emails
  for select using (user_id = public.current_user_id());

drop policy if exists "service role access labels" on public.label_configs;
create policy "service role access labels" on public.label_configs
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists "user access labels" on public.label_configs;
create policy "user access labels" on public.label_configs
  for select using (user_id = public.current_user_id());

drop policy if exists "service role access agent runs" on public.agent_runs;
create policy "service role access agent runs" on public.agent_runs
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists "user select own agent runs" on public.agent_runs;
create policy "user select own agent runs" on public.agent_runs
  for select using (user_id = public.current_user_id());

-- Trigger to keep updated_at fresh
create or replace function public.set_agent_runs_updated_at() returns trigger as $$
begin
  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists agent_runs_set_updated_at on public.agent_runs;
create trigger agent_runs_set_updated_at
  before update on public.agent_runs
  for each row execute function public.set_agent_runs_updated_at();
```

Review and adjust policies if you prefer different access patterns (e.g., broader insert/update permissions for authenticated users).

## Option A – Supabase SQL Editor
1. Open your project at https://app.supabase.com/.
2. Go to **SQL Editor → New query**.
3. Paste the SQL block above.
4. Click **Run** and verify results in the table browser.

## Option B – REST API (execute SQL)
Supabase exposes a PostgREST endpoint you can call with the service role key. Example using `curl`:

```bash
PROJECT_ID="your-project-ref"
SERVICE_ROLE_KEY="service-role-key"

SQL=$(cat <<'SQL'
create table if not exists public.users (
  id uuid primary key,
  email text not null,
  created_at timestamptz default now()
);
SQL
)

curl "https://${PROJECT_ID}.supabase.co/rest/v1/rpc/execute_sql" \
  -H "Content-Type: application/json" \
  -H "apikey: ${SERVICE_ROLE_KEY}" \
  -H "Authorization: Bearer ${SERVICE_ROLE_KEY}" \
  --data "{\"query\":\"${SQL//$'\n'/ }\"}"
```

Notes:
- Use the **service role key** for schema changes. Keep it secret.
- Escape newlines when embedding SQL in JSON (as shown above).
- Repeat for additional tables/policies (`gmail_tokens`, `emails`, `label_configs`, `agent_runs`).

## Option C – Direct Postgres Connection
Supabase provides a connection string under **Settings → Database**. Use `psql`:

```bash
psql "postgresql://postgres:<db-password>@<host>:6543/postgres"
\i path/to/schema.sql
```

## Rollback & Versioning
- Save executed SQL scripts under `supabase/sql/` (or similar) so changes are tracked in git.
- Add a short README alongside the scripts explaining the order of execution.
- For destructive changes, create a paired `*_down.sql` script to reverse the migration manually.

## Verifying Changes
1. Refresh the Supabase table view to confirm column definitions.
2. Run backend unit tests (`pytest backend/tests -q`).
3. Optionally issue a PostgREST request to confirm the API reflects new columns:
   ```bash
   curl "https://${PROJECT_ID}.supabase.co/rest/v1/emails?select=id,subject" \
     -H "apikey: ${SERVICE_ROLE_KEY}" \
     -H "Authorization: Bearer ${SERVICE_ROLE_KEY}"
   ```
