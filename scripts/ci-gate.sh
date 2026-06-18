#!/usr/bin/env bash
# ci-gate.sh — Evaluate a completed Argus scan against a security policy.
# Exits 0 if the scan passes all policies, non-zero otherwise.
#
# Usage:
#   ci-gate.sh --scan-id <uuid> [--policy-id <uuid>] [--api-url <url>] [--api-key <key>]
#
# Environment variables (override flags):
#   ARGUS_API_URL   Base URL of the Argus API (default: http://localhost:8000)
#   ARGUS_API_KEY   Bearer token for authentication
#   ARGUS_POLICY_ID Policy UUID to evaluate against (optional; evaluates all active policies if omitted)

set -euo pipefail

SCAN_ID=""
POLICY_ID="${ARGUS_POLICY_ID:-}"
API_URL="${ARGUS_API_URL:-http://localhost:8000}"
API_KEY="${ARGUS_API_KEY:-}"

usage() {
  echo "Usage: $0 --scan-id <uuid> [--policy-id <uuid>] [--api-url <url>] [--api-key <key>]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scan-id)   SCAN_ID="$2";   shift 2 ;;
    --policy-id) POLICY_ID="$2"; shift 2 ;;
    --api-url)   API_URL="$2";   shift 2 ;;
    --api-key)   API_KEY="$2";   shift 2 ;;
    *) usage ;;
  esac
done

[[ -z "$SCAN_ID" ]] && { echo "ERROR: --scan-id is required"; usage; }

AUTH_HEADER=""
[[ -n "$API_KEY" ]] && AUTH_HEADER="-H \"Authorization: Bearer ${API_KEY}\""

_curl() {
  if [[ -n "$API_KEY" ]]; then
    curl -sf -H "Authorization: Bearer ${API_KEY}" "$@"
  else
    curl -sf "$@"
  fi
}

echo "=== Argus CI Gate ==="
echo "Scan ID  : $SCAN_ID"
echo "API URL  : $API_URL"

# Fetch compliance report
REPORT=$(_curl "${API_URL}/api/v1/scans/${SCAN_ID}/report")
TOTAL=$(echo "$REPORT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['total_findings'])")
RISK=$(echo "$REPORT"  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['risk_score'])")
echo "Findings : $TOTAL  |  Risk score: $RISK"

OVERALL_PASS=0

if [[ -n "$POLICY_ID" ]]; then
  # Evaluate a specific policy
  RESULT=$(_curl -X POST "${API_URL}/api/v1/policies/${POLICY_ID}/evaluate/${SCAN_ID}")
  PASSED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print('true' if d['passed'] else 'false')")
  echo ""
  echo "Policy evaluation:"
  echo "$RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
status = 'PASS' if d['passed'] else 'FAIL'
print(f\"  [{status}] {d['policy_name']}\")
for v in d.get('violations', []):
    print(f\"    - {v['rule']}: actual={v['actual']}, limit={v['limit']}\")
"
  if [[ "$PASSED" == "false" ]]; then
    OVERALL_PASS=1
  fi
else
  # Evaluate against all active policies
  POLICIES=$(_curl "${API_URL}/api/v1/policies/?active_only=true")
  POLICY_COUNT=$(echo "$POLICIES" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
  echo "Active policies: $POLICY_COUNT"

  if [[ "$POLICY_COUNT" -eq 0 ]]; then
    echo "No active policies — scan passes by default."
  else
    echo ""
    echo "Policy evaluations:"
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      pname=$(echo "$POLICIES" | python3 -c "import json,sys; ps=json.load(sys.stdin); p=next(p for p in ps if p['id']=='${pid}'); print(p['name'])")
      RESULT=$(_curl -X POST "${API_URL}/api/v1/policies/${pid}/evaluate/${SCAN_ID}")
      PASSED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print('true' if d['passed'] else 'false')")
      STATUS="PASS"
      [[ "$PASSED" == "false" ]] && { STATUS="FAIL"; OVERALL_PASS=1; }
      echo "  [$STATUS] $pname"
      if [[ "$PASSED" == "false" ]]; then
        echo "$RESULT" | python3 -c "
import json, sys
for v in json.load(sys.stdin).get('violations', []):
    print(f\"    - {v['rule']}: actual={v['actual']}, limit={v['limit']}\")
"
      fi
    done < <(echo "$POLICIES" | python3 -c "import json,sys; [print(p['id']) for p in json.load(sys.stdin)]")
  fi
fi

echo ""
if [[ "$OVERALL_PASS" -eq 0 ]]; then
  echo "RESULT: PASSED"
else
  echo "RESULT: FAILED — scan did not meet policy requirements"
fi

exit $OVERALL_PASS
