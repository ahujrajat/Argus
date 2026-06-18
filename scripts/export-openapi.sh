#!/usr/bin/env bash
# Export the Argus OpenAPI 3.1 schema and optionally regenerate the TypeScript client.
#
# Usage:
#   ./scripts/export-openapi.sh                  # export JSON only
#   ./scripts/export-openapi.sh --gen-client      # export + regenerate TS client
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SCHEMA_OUT="$REPO_ROOT/surfaces/dashboard/src/api/openapi.json"
GEN_CLIENT=false

for arg in "$@"; do
  case "$arg" in
    --gen-client) GEN_CLIENT=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

echo "Exporting OpenAPI schema..."
cd "$REPO_ROOT"
source .venv/bin/activate 2>/dev/null || true

python - <<'PYEOF'
import json, sys
sys.path.insert(0, ".")
from core.api.app import create_app

app = create_app()
schema = app.openapi()
out_path = "surfaces/dashboard/src/api/openapi.json"
with open(out_path, "w") as f:
    json.dump(schema, f, indent=2)
    f.write("\n")
print(f"Schema written to {out_path} ({len(schema.get('paths', {}))} paths)")
PYEOF

if $GEN_CLIENT; then
  echo "Regenerating TypeScript client..."
  cd "$REPO_ROOT/surfaces/dashboard"
  if ! command -v npx &>/dev/null; then
    echo "npx not found — install Node.js to regenerate the TypeScript client" >&2
    exit 1
  fi
  npx openapi-typescript ../../../surfaces/dashboard/src/api/openapi.json \
    --output src/api/schema.d.ts
  echo "TypeScript types written to surfaces/dashboard/src/api/schema.d.ts"
fi

echo "Done."
