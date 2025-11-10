#!/usr/bin/env bash
# Script to purge all deprecated column references from codebase
# Run this from the project root: bash PURGE_DEPRECATED_COLUMNS.sh

set -e

echo "========================================="
echo "PURGING DEPRECATED COLUMNS"
echo "========================================="

# Backend - Pattern Learning Service
echo "Updating pattern_learning_service.py..."
sed -i '' 's/request\.applied_label/request.label/g' backend/app/services/pattern_learning_service.py

# Backend - Label Service: Update PatternExtractionRequest instantiation
echo "Updating label_service.py pattern extraction..."
sed -i '' 's/applied_label=applied_label,/label=applied_label,/g' backend/app/services/label_service.py

# Backend - Response schemas
echo "Updating ApplyLabelResponse schema..."
sed -i '' 's/applied_label: str/label: str/g' backend/app/schemas/labels.py

# Frontend - Remove deprecated fields from TypeScript interfaces
echo "Updating frontend IPC types..."
cat > /tmp/ipc_patch.txt <<'EOF'
  // DEPRECATED: Old fields (for backward compatibility)
  agentSuggestion?: string | null
  appliedLabel?: string | null
  labelAppliedAt?: string | null
EOF

# Remove the deprecated fields section from ipc.ts
sed -i '' '/DEPRECATED.*Old fields/,/labelAppliedAt\?:/d' electron-app/src/shared/ipc.ts

# Update ApplyLabelResponse in ipc.ts
sed -i '' 's/appliedLabel: string/label: string/g' electron-app/src/shared/ipc.ts

# Frontend - Update IPC handler
echo "Updating Electron main process..."
sed -i '' '/DEPRECATED.*Old fields/,/labelAppliedAt\?:/d' electron-app/electron/main/index.ts
sed -i '' 's/appliedLabel: result\.applied_label,/label: result.label,/g' electron-app/electron/main/index.ts

# Frontend - Simplify filtering logic
echo "Updating App.tsx filtering..."
sed -i '' 's/email\.label ?? email\.appliedLabel ?? email\.agentSuggestion ?? null/email.label ?? null/g' electron-app/src/App.tsx
sed -i '' '/appliedLabel:/d' electron-app/src/App.tsx
sed -i '' '/agentSuggestion:/d' electron-app/src/App.tsx

# Tests
echo "Updating tests..."
sed -i '' 's/applied_labels/labels/g' backend/tests/conftest.py
sed -i '' 's/appliedLabel/label/g' backend/tests/test_routes.py

echo ""
echo "========================================="
echo "✅ PURGE COMPLETE"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Remove update_email_label() from supabase_service.py manually"
echo "2. Drop database columns with migration SQL"
echo "3. Run tests: uv run pytest"
echo "4. Rebuild Electron app: cd electron-app && pnpm build"
echo ""
