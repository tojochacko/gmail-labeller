# Debug: Database Update Showing Success But Values Stay NULL

## Problem
Logs show "1 row(s) updated" but database query shows NULL values for:
- `applied_label`
- `label_applied_at`
- `sender_domain`

However, `updated_at` timestamp DOES change, proving the row was touched.

---

## Diagnostic Steps

### 1. Check for Database Triggers

Run this in **Supabase SQL Editor**:

```sql
-- Check if there are any triggers on the emails table
SELECT
    trigger_name,
    event_manipulation,
    action_statement,
    action_timing
FROM information_schema.triggers
WHERE event_object_table = 'emails';
```

**Expected**: Should show only `update_emails_updated_at` trigger (for updating the `updated_at` column).

**If you see other triggers**, they might be interfering with the updates.

---

### 2. Test Direct Update (Bypass ORM)

Run this SQL directly to test if Supabase allows updates:

```sql
-- Direct update test
UPDATE emails
SET
    applied_label = 'Test Important',
    label_applied_at = NOW(),
    sender_domain = 'test.com'
WHERE id = 'af964cec-30c9-4678-bff9-36a7f5e04ad5';

-- Verify the update
SELECT
    id,
    gmail_message_id,
    applied_label,
    label_applied_at,
    sender_domain,
    updated_at
FROM emails
WHERE id = 'af964cec-30c9-4678-bff9-36a7f5e04ad5';
```

**If this works**, the issue is with the Python client.
**If this doesn't work**, the issue is with RLS policies or database constraints.

---

### 3. Check RLS Policies

```sql
-- View RLS policies on emails table
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE tablename = 'emails';
```

**Expected**: Should show `emails_policy` with `USING (user_id = auth.uid())`.

**Important**: When using the SERVICE_ROLE_KEY, RLS should be bypassed. But verify with:

```sql
-- Check if RLS is enabled on emails table
SELECT
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables
WHERE tablename = 'emails';
```

If `rowsecurity` is `true` and you're somehow not using the service role key properly, updates might fail silently.

---

### 4. Verify Column Constraints

```sql
-- Check for any constraints on the columns
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'emails'
AND column_name IN ('applied_label', 'label_applied_at', 'sender_domain', 'sender_email')
ORDER BY column_name;
```

---

### 5. Check if Update is Actually Reaching Database

```sql
-- Enable query logging (if you have access)
-- Then run the label application again and check the logs

-- Or check the last queries on the table:
SELECT
    query,
    query_start,
    state
FROM pg_stat_activity
WHERE datname = current_database()
AND query LIKE '%emails%'
ORDER BY query_start DESC
LIMIT 10;
```

---

## Temporary Workaround: Manual Update

While debugging, you can manually verify the columns work:

```sql
-- Manual test
UPDATE emails
SET
    applied_label = 'Important',
    label_applied_at = '2025-11-09 14:52:35+00',
    sender_domain = 'example.com',
    sender_email = 'sender@example.com'
WHERE gmail_message_id = '19a68d7ee1552467';

-- Verify
SELECT * FROM emails WHERE gmail_message_id = '19a68d7ee1552467';
```

---

## Enhanced Logging

I've added more detailed logging to show the **actual response data** from Supabase.

**Restart your backend** and try labeling again. The new logs will show:

```
📊 Raw Supabase response object: {...}
📊 Response type: <class '...'>
📊 Response.__dict__: {...}
📋 Returned row values: applied_label=..., label_applied_at=..., sender_domain=...
```

This will tell us if Supabase is returning the updated values but they're not being persisted, or if Supabase never received the update command properly.

---

## Possible Root Causes

### 1. **Transaction Rollback** (Most Likely)
- Some part of the code is rolling back the transaction
- Check if there's error handling that's causing a rollback

### 2. **RLS Policy Issue**
- Even with service role key, there might be a policy issue
- Try temporarily disabling RLS:
  ```sql
  ALTER TABLE emails DISABLE ROW LEVEL SECURITY;
  ```
  Test labeling, then re-enable:
  ```sql
  ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
  ```

### 3. **Column Name Mismatch**
- Unlikely since columns exist, but double-check exact names

### 4. **Supabase Client Cache**
- The client might be caching stale connection info
- Restart backend completely (not just reload)

### 5. **Database Replication Lag**
- Very unlikely in Supabase, but possible
- Wait 5-10 seconds after labeling, then query

---

## Next Steps

1. **Run the direct UPDATE SQL test** (Step 2 above)
2. **Restart backend** to get enhanced logging
3. **Apply a label** and capture the new detailed logs
4. **Share**:
   - The direct SQL test results
   - The new backend log output (especially the "📊 Returned row values" line)
   - The trigger check results

This will pinpoint whether it's a database issue, RLS issue, or client issue.
