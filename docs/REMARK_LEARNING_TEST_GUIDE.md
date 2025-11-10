# Re-Mark Learning Test Guide

## 🎉 What's New

Your auto-labeling system now has **accelerated learning from re-marks**!

When you correct an auto-labeled email (or change any existing label), the system:
- ✅ Detects the label change (re-mark)
- ✅ Applies **2x weight** to patterns for the NEW label
- ✅ Learns faster from your corrections
- ✅ Improves accuracy for future emails

---

## 🔄 Restart Backend First

```bash
cd /workspaces/autogen-test
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
```

---

## 🧪 Test Scenario: Re-Mark Learning

### Step 1: Create Initial Pattern (Manual Label)

1. **Fetch emails** in Electron app
2. **Find an email** from a specific domain (e.g., `example.com`)
3. **Label it "Important"**
4. Check backend logs:
   ```
   🏷️  APPLY_LABEL START: ...
   ✅ Email found in database: ...
   📝 Updating database with NEW SCHEMA: label=Important, source=manual, confidence=1.0
   ✅ DATABASE UPDATE SUCCESS (new schema): ...
   Starting pattern extraction (normal weight)...
   ✅ Pattern extraction completed
   🏷️  APPLY_LABEL COMPLETE: label=AI:Important, is_remark=False
   ```

**What happened**: Pattern created with weight **1.0** (normal)

---

### Step 2: Auto-Label Similar Email

1. **Fetch new emails**
2. **Look for an email** from the same domain (`example.com`)
3. Check backend logs:
   ```
   🆕 NEW EMAIL: ... from user@example.com
   🤖 AUTO-LABELED: 'Important' (confidence: 0.652, matched: example.com)
   ✅ Applied 'Important' to Gmail
   ```

**What happened**: New email auto-labeled based on learned pattern

---

### Step 3: Re-Mark (Correct the Label)

Now let's simulate a correction (you decide the auto-label was wrong):

1. **Find the auto-labeled email**
2. **Change the label** to "Not Important"
3. **Check backend logs** for re-mark detection:
   ```
   🏷️  APPLY_LABEL START: label_name=Not Important
   ✅ Email found in database: id=..., subject=...
   📝 RE-MARK DETECTED: 'Important' → 'Not Important' (will apply 2x learning weight)
   ✅ Gmail label 'AI:Not Important' applied successfully
   📝 Updating database with NEW SCHEMA: label=Not Important, source=manual, confidence=1.0
   ✅ DATABASE UPDATE SUCCESS (new schema): ...
   🚀 ACCELERATED LEARNING: Applying 2x weight for re-mark 'Important' → 'Not Important'
   ✅ Re-mark learning complete: patterns updated with 2x weight
   🏷️  APPLY_LABEL COMPLETE: label=AI:Not Important, is_remark=True
   ```

**Key Log Messages**:
- ✅ `📝 RE-MARK DETECTED` - System recognized the label change
- ✅ `🚀 ACCELERATED LEARNING` - 2x weight being applied
- ✅ `is_remark=True` - Confirmation that re-mark was processed

**What happened**: Patterns for "Not Important" from `example.com` now have weight **2.0** (2x multiplier)!

---

### Step 4: Verify Pattern Weight in Database

```sql
-- Check pattern weights
SELECT
    pattern_type,
    pattern_value,
    label_type,
    pattern_weight,
    confidence_score,
    occurrence_count,
    times_applied,
    times_corrected
FROM label_patterns
WHERE pattern_value = 'example.com'
ORDER BY updated_at DESC;
```

**Expected Result**:
```
pattern_type | pattern_value | label_type      | pattern_weight | confidence_score
-------------+---------------+-----------------+----------------+-----------------
domain       | example.com   | Not Important   | 2.0            | 0.50
domain       | example.com   | Important       | 1.0            | 0.50
```

**Analysis**:
- "Not Important" pattern has **weight 2.0** (from re-mark)
- "Important" pattern has **weight 1.0** (original)
- Next similar email will be auto-labeled "Not Important" with higher confidence!

---

## 🎯 Expected Behavior After Re-Mark

### Next Email from Same Domain

1. **Fetch new emails**
2. **Email from `example.com` arrives**
3. **Auto-labeling calculation**:
   ```
   Pattern matches:
   - Domain "example.com" → "Important" (weight 1.0, confidence 0.5)
   - Domain "example.com" → "Not Important" (weight 2.0, confidence 0.5)

   Weighted scores:
   - Important: 0.5 (domain weight) × 0.5 (confidence) × 1.0 (weight) = 0.25
   - Not Important: 0.5 (domain weight) × 0.5 (confidence) × 2.0 (weight) = 0.50

   Winner: "Not Important" (0.50 > 0.25, above 0.4 threshold)
   ```

4. **Result**: Email auto-labeled **"Not Important"**! ✅

**What this proves**: Re-marks make learning 2x faster!

---

## 🔍 Log Messages to Watch For

### ✅ Success Indicators

**Re-Mark Detection**:
```
📝 RE-MARK DETECTED: 'Important' → 'Not Important' (will apply 2x learning weight)
```

**New Schema Update**:
```
📝 Updating database with NEW SCHEMA: label=Not Important, source=manual, confidence=1.0
✅ DATABASE UPDATE SUCCESS (new schema): email ... labeled as 'Not Important'
```

**Accelerated Learning**:
```
🚀 ACCELERATED LEARNING: Applying 2x weight for re-mark 'Important' → 'Not Important'
✅ Re-mark learning complete: patterns updated with 2x weight
```

**Confirmation**:
```
🏷️  APPLY_LABEL COMPLETE: label=AI:Not Important, is_remark=True
```

---

### ⚠️ Things to Check If Re-Mark Not Working

**1. Old label not detected**:
```
First-time label: 'Not Important' (no previous label)
```
→ **Cause**: Email didn't have a label before
→ **Solution**: Label an email first, then change it

**2. Same label reapplied**:
```
Same label reapplied: 'Important' (no re-mark)
```
→ **Cause**: Clicking "Important" on already "Important" email
→ **Solution**: Change to a different label

**3. Re-mark learning failed**:
```
⚠️  Re-mark learning failed (non-fatal): ...
```
→ **Cause**: Error in pattern update
→ **Solution**: Check full error message in logs

---

## 📊 Database Verification Queries

### Check Email Labels

```sql
-- View recent label updates with new schema
SELECT
    gmail_message_id,
    subject,
    sender_email,
    label,
    label_confidence,
    label_source,
    last_updated_by,
    labeled_at
FROM emails
WHERE label IS NOT NULL
ORDER BY labeled_at DESC
LIMIT 10;
```

**What to look for**:
- `label_source = 'manual'` for user-applied labels
- `label_source = 'auto'` for auto-labeled emails
- `label_confidence = 1.0` for manual labels
- `label_confidence < 1.0` for auto labels

---

### Track Pattern Learning

```sql
-- View pattern performance
SELECT
    pattern_type,
    pattern_value,
    label_type,
    pattern_weight,
    confidence_score,
    occurrence_count,
    times_applied,
    times_corrected,
    CASE
        WHEN times_applied > 0
        THEN ROUND((times_applied - times_corrected)::numeric / times_applied * 100, 1)
        ELSE 0
    END as success_rate_percent
FROM label_patterns
ORDER BY pattern_weight DESC, confidence_score DESC
LIMIT 20;
```

**What to look for**:
- `pattern_weight = 2.0+` indicates re-marked patterns
- `times_corrected > 0` shows patterns that were wrong
- `success_rate_percent` shows accuracy (higher is better)

---

### Find Re-Marks

```sql
-- This requires tracking (could be future enhancement)
-- For now, check for manual labels that replaced auto labels:

SELECT
    gmail_message_id,
    subject,
    sender_email,
    label,
    label_source,
    label_confidence,
    labeled_at
FROM emails
WHERE label_source = 'manual'
AND labeled_at > NOW() - INTERVAL '1 hour'
ORDER BY labeled_at DESC;
```

---

## 🎓 Understanding the Math

### Normal Pattern Creation (First-time label)
```
Pattern weight: 1.0 (default)
Contribution to confidence: base_confidence × type_weight × 1.0
```

### Re-Mark Pattern Update
```
Pattern weight: 1.0 + (2.0 - 1.0) = 2.0 (2x multiplier)
Contribution to confidence: base_confidence × type_weight × 2.0
```

### Example Calculation

**Email**: `subject: "Meeting tomorrow", from: boss@company.com`

**Patterns**:
- Domain `company.com` → "Important" (weight 1.0, confidence 0.8)
- Keyword `meeting` → "Not Important" (weight 2.0, confidence 0.6) ← Re-marked!

**Score Calculation**:
```
Important score:
  Domain: 0.8 (confidence) × 0.5 (domain weight) × 1.0 (pattern weight) = 0.40

Not Important score:
  Keyword: 0.6 (confidence) × 0.3 (keyword weight) × 2.0 (pattern weight) = 0.36

Winner: Important (0.40 > 0.36, both above 0.4 threshold)
```

The re-mark gave "Not Important" a significant boost (0.36 vs 0.18 without 2x weight)!

---

## 🚀 Real-World Scenario

### Day 1: Initial Learning
- Manually label 5 emails from `newsletter.com` as "Not Important"
- Pattern created: `domain=newsletter.com → Not Important` (weight 1.0)

### Day 2: Auto-Labeling
- New email from `newsletter.com` arrives
- Auto-labeled "Not Important" (confidence 0.60)

### Day 3: User Correction
- User realizes this specific newsletter IS important
- Re-marks email as "Important"
- System applies 2x weight: `domain=newsletter.com → Important` (weight 2.0)

### Day 4: Improved Accuracy
- Next email from `newsletter.com`
- Auto-labeled "Important" (confidence 0.75, higher due to 2x weight!)
- User doesn't need to correct again ✅

**Result**: System learned in 1 correction what would have taken 2-3 manual labels!

---

## ✅ Success Checklist

After completing this test, you should have verified:

- [ ] Re-mark detected in logs (`📝 RE-MARK DETECTED`)
- [ ] 2x weight applied (`🚀 ACCELERATED LEARNING`)
- [ ] Database updated with new schema (`label`, `label_source=manual`)
- [ ] Pattern weight increased to 2.0 in `label_patterns` table
- [ ] Next similar email auto-labeled with higher confidence
- [ ] Logs show `is_remark=True` for label changes

---

## 🎉 What You've Achieved

With re-mark learning enabled, your system now:
- ✅ Learns **2x faster** from corrections
- ✅ Adapts quickly to changing user preferences
- ✅ Reduces manual labeling burden over time
- ✅ Maintains backward compatibility (works with old data too)

**Next step**: Continue to Priority 2 (API routes and frontend updates) or start using the system and watch it learn! 🚀

---

## 📝 Notes

- **Re-marks only trigger for label CHANGES** (not reapplying same label)
- **Both old and new schema fields are checked** (backward compatible)
- **Pattern learning is non-fatal** (won't break label application if it fails)
- **2x weight can compound** (re-marking multiple times increases weight up to 5.0 max)

---

**Questions?** Check backend logs for detailed flow, or query the database to see pattern weights in action!
