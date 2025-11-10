# Complete Deprecated Columns Purge - Remaining Manual Steps

## ✅ COMPLETED

The following have been successfully purged:

1. **Backend EmailItem schema** - Removed `agent_suggestion`, `applied_label`, `label_applied_at` fields
2. **Agent Service** - Updated to use `update_email_with_new_schema()`
3. **Label Service** - Updated manual labeling to use new schema
4. **Pattern Learning** - Updated to use `request.label` instead of `request.applied_label`
5. **Email Stats** - Removed fallback logic to deprecated fields
6. **Supabase Service** - Removed `update_email_suggestion()` method

## 🔧 REMAINING MANUAL EDITS

### 1. Remove deprecated Supabase method `update_email_label()`

**File**: `backend/app/services/supabase_service.py`
**Lines**: 614-716

Delete the entire `update_email_label()` and `_update_email_label_sync()` methods. They are no longer used since label_service now calls `update_email_with_new_schema()`.

```python
# DELETE THIS ENTIRE BLOCK (lines 614-716):
async def update_email_label(...):
    ...
def _update_email_label_sync(...):
    ...
```

---

### 2. Update ApplyLabelResponse schema

**File**: `backend/app/schemas/labels.py`
**Line**: 23

```python
# CHANGE FROM:
applied_label: str

# TO:
label: str
```

---

### 3. Update Electron IPC response mapping

**File**: `electron-app/electron/main/index.ts`
**Line**: 295

```typescript
// CHANGE FROM:
appliedLabel: result.applied_label,

// TO:
label: result.label,
```

---

###4. Remove deprecated fields from frontend TypeScript types

**File**: `electron-app/src/shared/ipc.ts`
**Lines**: 44-47

```typescript
// DELETE THESE LINES:
  // DEPRECATED: Old fields (for backward compatibility)
  agentSuggestion?: string | null
  appliedLabel?: string | null
  labelAppliedAt?: string | null
```

**Lines**: 73

```typescript
// CHANGE FROM:
  appliedLabel: string

// TO:
  label: string
```

---

### 5. Remove deprecated fields from Electron main process type

**File**: `electron-app/electron/main/index.ts`
**Lines**: 158-161

```typescript
// DELETE THESE LINES:
  // DEPRECATED: Old fields
  agentSuggestion?: string | null
  appliedLabel?: string | null
  labelAppliedAt?: string | null
```

**Lines**: 195-198

```typescript
// DELETE THESE LINES from mapEmailResponse function:
    // DEPRECATED: Old fields (for backward compatibility)
    agentSuggestion: item.agentSuggestion ?? null,
    appliedLabel: item.appliedLabel ?? null,
    labelAppliedAt: item.labelAppliedAt ?? null,
```

---

### 6. Simplify frontend filtering logic

**File**: `electron-app/src/App.tsx`
**Line**: 325

```typescript
// CHANGE FROM:
return email.label ?? email.appliedLabel ?? email.agentSuggestion ?? null

// TO:
return email.label ?? null
```

**Lines**: 339-352 (Debug logging)**

Remove the deprecated field references from console.log:

```typescript
// CHANGE FROM:
console.log('Important emails:', importantEmails.length, importantEmails.map(e => ({
  subject: e.subject,
  effectiveLabel: getEffectiveLabel(e),
  label: e.label,
  appliedLabel: e.appliedLabel,  // ← REMOVE
  agentSuggestion: e.agentSuggestion  // ← REMOVE
})))

// TO:
console.log('Important emails:', importantEmails.length, importantEmails.map(e => ({
  subject: e.subject,
  label: e.label,
})))
```

---

### 7. Update tests

**File**: `backend/tests/conftest.py`
**Lines**: 86, 120

```python
# CHANGE FROM:
self.applied_labels: list[tuple[str, str]] = []
...
self.applied_labels.append((message_id, label_id))

# TO:
self.labels: list[tuple[str, str]] = []
...
self.labels.append((message_id, label_id))
```

**File**: `backend/tests/test_routes.py`
**Line**: 51

```python
# CHANGE FROM:
assert response.json()["applied_label"] == "AUTO_LABEL"

# TO:
assert response.json()["label"] == "AUTO_LABEL"
```

**File**: `backend/tests/conftest.py`
**Line**: 142

```python
# CHANGE FROM:
return ApplyLabelResponse(success=True, applied_label=request.label_name)

# TO:
return ApplyLabelResponse(success=True, label=request.label_name)
```

---

### 8. Drop database columns

**File**: `database/migrations/003_drop_deprecated_columns.sql` (create this file)

```sql
-- Migration 003: Drop Deprecated Label Columns
-- Drop old label columns after migration to consolidated schema

BEGIN;

-- Drop indexes first
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

    RAISE NOTICE '✅ All deprecated columns successfully dropped';
END $$;

COMMIT;
```

**Run in Supabase SQL Editor** after verifying all code changes work correctly.

---

## 🧪 TESTING CHECKLIST

After completing all manual steps above:

### Backend Tests
```bash
cd /workspaces/autogen-test
uv run pytest backend/tests/ -v
```

Should all pass.

### Frontend Build
```bash
# On host machine
cd /path/to/autogen-test/electron-app
pnpm build
```

Should compile without TypeScript errors.

### End-to-End Test
1. Start backend: `uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000`
2. Start frontend: `pnpm dev` (on host machine)
3. Fetch emails - should see labels correctly
4. Manually mark an email - should update to new schema
5. Check database - new `label` column should be populated, old columns should not exist (after running migration 003)

---

## 📊 VERIFICATION

After all changes, verify:

```bash
# Backend - No references to deprecated fields
rg "agent_suggestion|applied_label|label_applied_at" backend/app/

# Frontend - No references to deprecated fields
rg "agentSuggestion|appliedLabel|labelAppliedAt" electron-app/src/ electron-app/electron/
```

Both should return NO matches (except in migration files).

---

## 🎯 SUMMARY

**Total Changes Required**: 8 manual edits + 1 database migration

**Estimated Time**: 15-20 minutes

**Risk Level**: Low (all changes are straightforward removals/renames)

**Rollback Plan**: Git revert if issues occur

Once complete, your codebase will be 100% purged of deprecated columns! 🎉
