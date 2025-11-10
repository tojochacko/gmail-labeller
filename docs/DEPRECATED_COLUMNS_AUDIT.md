# Deprecated Columns Audit Report

**Date**: 2025-11-10
**Migration**: 002_consolidate_label_schema
**Scope**: Complete codebase audit for old label column references

---

## Executive Summary

After migrating from a dual-column label system (`agent_suggestion` + `applied_label`) to a consolidated single-column system (`label` + metadata), this audit identifies all remaining references to deprecated columns across the codebase.

**Old Schema (Deprecated)**:
- `agent_suggestion` - AI-generated label suggestions
- `applied_label` - User-applied labels
- `label_applied_at` - Timestamp when label was applied

**New Schema (Current)**:
- `label` - Consolidated label field
- `label_confidence` - Confidence score (0.0-1.0)
- `label_source` - Source: 'auto', 'manual', or 'agent'
- `labeled_at` - Timestamp when labeled
- `last_updated_by` - Last updater: 'auto', 'user', or 'agent'

---

## Category 1: ✅ KEEP (Required for Backward Compatibility)

These references MUST remain for transition period and backward compatibility:

### Backend - Schema Definitions

**File**: `backend/app/schemas/email.py`
- **Lines 82-92**: EmailItem model deprecated field definitions
- **Purpose**: Define deprecated fields for Pydantic model validation
- **Status**: ✅ Keep - Required for data migration transition period

```python
# DEPRECATED: Old Label Fields (Pre-Migration)
agent_suggestion: Optional[str] = Field(default=None, description="[DEPRECATED]...")
applied_label: Optional[str] = Field(default=None, description="[DEPRECATED]...")
label_applied_at: Optional[datetime] = Field(default=None, description="[DEPRECATED]...")
```

### Backend - Email Service

**File**: `backend/app/services/email_service.py`
- **Lines 86-90**: Preserve deprecated fields when fetching existing emails
- **Line 265-267**: Initialize deprecated fields to None for new emails
- **Purpose**: Maintain backward compatibility during migration
- **Status**: ✅ Keep - Ensures gradual migration without data loss

### Backend - Stats Calculation

**File**: `backend/app/routes/emails.py`
- **Lines 127-136**: Fallback to deprecated fields for stats calculation
- **Purpose**: Calculate stats from old fields if new schema not yet populated
- **Status**: ✅ Keep - Required during migration transition

### Frontend - Type Definitions

**File**: `electron-app/src/shared/ipc.ts`
- **Lines 44-47**: EmailItem interface deprecated fields
- **Lines 73**: ApplyLabelResponse.appliedLabel field
- **Purpose**: TypeScript type safety for deprecated fields
- **Status**: ✅ Keep - Required for IPC compatibility

**File**: `electron-app/electron/main/index.ts`
- **Lines 158-161**: BackendEmailItem type deprecated fields
- **Lines 195-198**: mapEmailResponse function mapping
- **Purpose**: Map backend response to frontend format
- **Status**: ✅ Keep - Required for backward compatibility

### Frontend - Filtering Logic

**File**: `electron-app/src/App.tsx`
- **Lines 324-325**: getEffectiveLabel function fallback logic
- **Lines 339-352**: Debug console logging (includes deprecated fields)
- **Purpose**: Prioritize new label field with fallback to deprecated fields
- **Status**: ✅ Keep - Critical for correct email categorization during transition

---

## Category 2: ⚠️ REVIEW (May Need Updates)

These references use old fields and should potentially be updated to use new schema:

### Backend - Agent Service (NEEDS UPDATE)

**File**: `backend/app/services/agent_service.py`
- **Lines 86-89, 167-170**: `update_email_suggestion()` calls
- **Current**: Updates `agent_suggestion` field
- **Recommended**: Update to use new `label` field with `label_source='agent'`
- **Impact**: Agent-generated suggestions not flowing to new schema

### Backend - Supabase Service (NEEDS UPDATE)

**File**: `backend/app/services/supabase_service.py`
- **Lines 154-162**: `update_email_suggestion()` method
- **Current**: Updates old `agent_suggestion` column
- **Recommended**: Create new method to update consolidated label fields
- **Impact**: Agent service still writing to deprecated column

### Backend - Label Service (MIXED - Partial Update Needed)

**File**: `backend/app/services/label_service.py`

**Lines 102-104**: ✅ Keep - Fallback logic for old label detection
```python
# Fallback to deprecated fields for backward compatibility
if not old_label:
    old_label = email.applied_label or email.agent_suggestion
```

**Lines 188-191**: ⚠️ NEEDS UPDATE - Pattern extraction uses old schema
```python
await self._pattern_learning.extract_patterns(
    PatternExtractionRequest(
        applied_label=request.label_name,  # Using old schema!
        ...
    )
)
```

**Lines 362-365**: ⚠️ NEEDS UPDATE - Direct write to old column
```python
await self._supabase.update_email_label(
    email_id=email.id,
    applied_label=applied_label,  # Writing to deprecated column!
    ...
)
```

**Recommended**: Update to use `update_email_with_new_schema()` instead

### Backend - Pattern Learning (NEEDS UPDATE)

**File**: `backend/app/services/pattern_learning_service.py`
- **Lines 165, 177**: Uses `request.applied_label`
- **Purpose**: Extract patterns from labeled emails
- **Impact**: Pattern learning still expects old schema
- **Recommended**: Update PatternExtractionRequest to use new schema

**File**: `backend/app/schemas/label_patterns.py`
- **Line 130**: `PatternExtractionRequest.applied_label` field
- **Recommended**: Rename to `label` to match new schema

---

## Category 3: 📊 DATABASE (Migration Complete, Columns Exist)

### Database Schema

**File**: `database/supabase_schema.sql`
- **Line 51**: `agent_suggestion TEXT` column definition
- **Status**: Still exists in database schema
- **Note**: Migration 002 added new columns but kept old ones

### Database Migrations

**File**: `database/migrations/002_consolidate_label_schema.sql`
- **Lines 33-52**: Data migration from old → new columns
- **Lines 133-135**: DROP statements commented out (not executed yet)
- **Status**: Migration complete, but old columns not dropped yet

**File**: `database/migrations/001_add_label_patterns.sql`
- **Lines 66-67, 70-71, 77**: Created `applied_label` and `label_applied_at` columns
- **Status**: Superseded by migration 002

---

## Category 4: ✅ TEST CODE (Appropriate Usage)

**File**: `backend/tests/conftest.py`
- **Lines 86, 120**: Test doubles tracking `applied_labels`
- **Status**: ✅ Keep - Test code appropriately mocking deprecated fields

**File**: `backend/tests/test_routes.py`
- **Line 51**: Assertion checking `applied_label` in response
- **Status**: ✅ Keep - Valid test for backward compatibility

---

## Priority Action Items

### 🔴 HIGH PRIORITY (Breaks Functionality)

1. **Agent Service Not Using New Schema**
   - **Files**: `agent_service.py`, `supabase_service.py`
   - **Issue**: Agent suggestions writing to `agent_suggestion` instead of `label`
   - **Impact**: Agent-generated labels not appearing in new UI
   - **Fix**: Replace `update_email_suggestion()` with `update_email_with_new_schema()`

2. **Label Service Manual Updates Using Old Schema**
   - **File**: `label_service.py` lines 362-365
   - **Issue**: Manual label applications writing to `applied_label` instead of `label`
   - **Impact**: Manual labels may not sync properly
   - **Fix**: Replace `update_email_label()` with `update_email_with_new_schema()`

### 🟡 MEDIUM PRIORITY (Technical Debt)

3. **Pattern Learning Schema Mismatch**
   - **Files**: `pattern_learning_service.py`, `label_patterns.py`
   - **Issue**: PatternExtractionRequest uses old `applied_label` field name
   - **Impact**: Code inconsistency, confusing for developers
   - **Fix**: Rename field to `label` for consistency

### 🟢 LOW PRIORITY (Future Cleanup)

4. **Database Column Cleanup**
   - **File**: `database/migrations/002_consolidate_label_schema.sql` lines 133-135
   - **Issue**: Deprecated columns still exist in database
   - **Impact**: Wasted storage, potential confusion
   - **Fix**: After 1-2 weeks of verification, uncomment DROP statements

5. **ApplyLabelResponse Field Name**
   - **File**: `backend/app/schemas/labels.py` line 23
   - **Issue**: Response uses `applied_label` instead of `label`
   - **Impact**: Minor API inconsistency
   - **Fix**: Rename to `label` (breaking change for API consumers)

---

## Recommendations

### Immediate Actions (This Week)

1. ✅ **Update Agent Service** to write to new `label` field
2. ✅ **Update Label Service** manual label writes to new schema
3. ✅ **Update Pattern Extraction** to use new field names
4. ✅ **Add integration tests** for new schema writes

### Short-term Actions (Next 1-2 Weeks)

5. ⏱️ **Monitor migration** - Ensure all new data uses new schema
6. ⏱️ **Verify old data** - Confirm migration script properly converted existing data
7. ⏱️ **Document cutover** - Set date for dropping old columns

### Long-term Actions (After 2+ Weeks)

8. 🗑️ **Drop deprecated columns** from database
9. 🗑️ **Remove deprecated fields** from Pydantic models
10. 🗑️ **Clean up fallback logic** in frontend and backend

---

## Migration Status Summary

| Component | Old Schema Usage | New Schema Usage | Status |
|-----------|------------------|------------------|--------|
| Email Fetch | ✅ Preserved | ✅ Primary | ✅ Complete |
| Auto-Labeling | N/A | ✅ Implemented | ✅ Complete |
| Manual Labeling | ⚠️ Still Writing | ⚠️ Partial | ⚠️ Needs Fix |
| Agent Suggestions | ⚠️ Still Writing | ❌ Not Used | ❌ Needs Fix |
| Pattern Learning | ⚠️ Old Field Names | ⚠️ Old Field Names | ⚠️ Needs Update |
| Frontend Display | ✅ Fallback Logic | ✅ Primary | ✅ Complete |
| Database | ✅ Columns Exist | ✅ Columns Exist | ⏳ Pending Cleanup |

---

## Conclusion

The schema migration is **mostly complete**, but there are critical gaps where new label writes are still going to deprecated columns:

**Working**:
- ✅ Auto-labeling system uses new schema
- ✅ Email fetching preserves both old and new fields
- ✅ Frontend correctly prioritizes new fields with fallback
- ✅ Stats calculation handles both schemas

**Broken**:
- ❌ Agent service writes to `agent_suggestion` instead of `label`
- ❌ Manual labeling writes to `applied_label` instead of `label`
- ❌ Pattern extraction expects old field names

**Next Steps**: Fix the HIGH PRIORITY items first to ensure all new label writes use the consolidated schema.
