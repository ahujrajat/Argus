#!/usr/bin/env bash
# surfaces/ci/argus-scan.sh
#
# Trigger an Argus security scan and gate on severity.
#
# Required env vars:
#   ARGUS_API_BASE   - e.g. http://localhost:8000  (default: http://localhost:8000)
#   ARGUS_TARGET     - target_ref for the scan (required)
#
# Optional env vars:
#   ARGUS_MODE           - at_rest | real_time  (default: at_rest)
#   ARGUS_APPROACH       - security approach    (default: penetration_testing)
#   ARGUS_PIPELINE       - pipeline config name (default: full-scan)
#   ARGUS_FAIL_ON        - comma-separated severities to fail on (default: critical,high)
#   ARGUS_TIMEOUT_SEC    - polling timeout in seconds (default: 600)
#   ARGUS_POLL_INTERVAL  - seconds between status checks (default: 10)

set -euo pipefail

API_BASE="${ARGUS_API_BASE:-http://localhost:8000}"
TARGET="${ARGUS_TARGET:?ARGUS_TARGET is required}"
MODE="${ARGUS_MODE:-at_rest}"
APPROACH="${ARGUS_APPROACH:-penetration_testing}"
PIPELINE="${ARGUS_PIPELINE:-full-scan}"
FAIL_ON="${ARGUS_FAIL_ON:-critical,high}"
TIMEOUT="${ARGUS_TIMEOUT_SEC:-600}"
POLL="${ARGUS_POLL_INTERVAL:-10}"

# ── helpers ──────────────────────────────────────────────────────────────────

_curl() { curl --silent --fail --show-error "$@"; }

_jq_required() {
  if ! command -v jq &>/dev/null; then
    echo "ERROR: jq is required but not found in PATH" >&2
    exit 1
  fi
}

_severity_matches() {
  local sev="$1"
  IFS=',' read -ra sevs <<< "$FAIL_ON"
  for s in "${sevs[@]}"; do
    [[ "$sev" == "$s" ]] && return 0
  done
  return 1
}

# ── main ─────────────────────────────────────────────────────────────────────

_jq_required

echo "=== Argus Security Scan ==="
echo "  Target:   $TARGET"
echo "  Mode:     $MODE"
echo "  Approach: $APPROACH"
echo "  Pipeline: $PIPELINE"
echo "  Fail on:  $FAIL_ON"
echo ""

# Trigger scan
TRIGGER_RESP=$(_curl -X POST "${API_BASE}/api/v1/scans/" \
  -H "Content-Type: application/json" \
  -d "{\"target_ref\":\"${TARGET}\",\"mode\":\"${MODE}\",\"approach\":\"${APPROACH}\",\"pipeline_config_name\":\"${PIPELINE}\"}")

SCAN_ID=$(echo "$TRIGGER_RESP" | jq -r '.scan_id')
echo "Scan started: $SCAN_ID"
echo ""

# Poll for completion
ELAPSED=0
while true; do
  STATUS_RESP=$(_curl "${API_BASE}/api/v1/scans/${SCAN_ID}")
  STATUS=$(echo "$STATUS_RESP" | jq -r '.status')

  echo "[${ELAPSED}s] Scan status: $STATUS"

  case "$STATUS" in
    completed) break ;;
    failed)
      echo "ERROR: Scan failed" >&2
      exit 2
      ;;
    cancelled)
      echo "ERROR: Scan was cancelled" >&2
      exit 2
      ;;
  esac

  if [[ $ELAPSED -ge $TIMEOUT ]]; then
    echo "ERROR: Timed out waiting for scan to complete after ${TIMEOUT}s" >&2
    exit 2
  fi

  sleep "$POLL"
  ELAPSED=$((ELAPSED + POLL))
done

echo ""
echo "=== Findings Summary ==="

FINDINGS_RESP=$(_curl "${API_BASE}/api/v1/scans/${SCAN_ID}/findings")
TOTAL=$(echo "$FINDINGS_RESP" | jq 'length')
echo "Total findings: $TOTAL"
echo ""

# Count by severity
for SEV in critical high medium low info; do
  COUNT=$(echo "$FINDINGS_RESP" | jq "[.[] | select(.severity == \"${SEV}\")] | length")
  printf "  %-10s %d\n" "$SEV" "$COUNT"
done
echo ""

# Gate on severity
FAIL=0
IFS=',' read -ra FAIL_SEVS <<< "$FAIL_ON"
for SEV in "${FAIL_SEVS[@]}"; do
  COUNT=$(echo "$FINDINGS_RESP" | jq "[.[] | select(.severity == \"${SEV}\" and .status != \"dismissed\")] | length")
  if [[ $COUNT -gt 0 ]]; then
    echo "GATE FAILED: $COUNT ${SEV} finding(s) found" >&2
    FAIL=1
  fi
done

if [[ $FAIL -eq 1 ]]; then
  echo "" >&2
  echo "Scan gate failed — see findings above." >&2
  exit 1
fi

echo "Scan gate passed."
