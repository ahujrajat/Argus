@echo off
REM ci-gate.bat — Evaluate a completed Argus scan against a security policy.
REM Exits 0 if the scan passes all policies, non-zero otherwise.
REM
REM Usage:
REM   ci-gate.bat --scan-id <uuid> [--policy-id <uuid>] [--api-url <url>] [--api-key <key>]
REM
REM Environment variables:
REM   ARGUS_API_URL   Base URL of the Argus API (default: http://localhost:8000)
REM   ARGUS_API_KEY   Bearer token for authentication
REM   ARGUS_POLICY_ID Policy UUID (optional)

setlocal enabledelayedexpansion

set SCAN_ID=
set POLICY_ID=%ARGUS_POLICY_ID%
set API_URL=%ARGUS_API_URL%
if not defined API_URL set API_URL=http://localhost:8000
set API_KEY=%ARGUS_API_KEY%
set OVERALL_PASS=0

:parse_args
if "%~1"=="" goto check_args
if /i "%~1"=="--scan-id"   ( set SCAN_ID=%~2&   shift & shift & goto parse_args )
if /i "%~1"=="--policy-id" ( set POLICY_ID=%~2& shift & shift & goto parse_args )
if /i "%~1"=="--api-url"   ( set API_URL=%~2&   shift & shift & goto parse_args )
if /i "%~1"=="--api-key"   ( set API_KEY=%~2&   shift & shift & goto parse_args )
echo Unknown argument: %~1
goto usage

:check_args
if not defined SCAN_ID (
    echo ERROR: --scan-id is required
    goto usage
)
goto main

:usage
echo Usage: %~nx0 --scan-id ^<uuid^> [--policy-id ^<uuid^>] [--api-url ^<url^>] [--api-key ^<key^>]
exit /b 1

:main
echo === Argus CI Gate ===
echo Scan ID  : %SCAN_ID%
echo API URL  : %API_URL%

REM Build auth header flag for curl
set AUTH_FLAG=
if defined API_KEY set AUTH_FLAG=-H "Authorization: Bearer %API_KEY%"

REM Fetch compliance report
curl -sf %AUTH_FLAG% "%API_URL%/api/v1/scans/%SCAN_ID%/report" -o "%TEMP%\argus_report.json"
if errorlevel 1 (
    echo ERROR: Failed to fetch compliance report for scan %SCAN_ID%
    exit /b 2
)

python -c "import json; d=json.load(open(r'%TEMP%\argus_report.json')); print('Findings :', d['total_findings'], ' | Risk score:', d['risk_score'])"

if defined POLICY_ID (
    REM Evaluate a specific policy
    curl -sf %AUTH_FLAG% -X POST "%API_URL%/api/v1/policies/%POLICY_ID%/evaluate/%SCAN_ID%" -o "%TEMP%\argus_eval.json"
    if errorlevel 1 (
        echo ERROR: Failed to evaluate policy %POLICY_ID%
        exit /b 2
    )
    python -c "
import json
d = json.load(open(r'%TEMP%\argus_eval.json'))
status = 'PASS' if d['passed'] else 'FAIL'
print(f\"  [{status}] {d['policy_name']}\")
for v in d.get('violations', []):
    print(f\"    - {v['rule']}: actual={v['actual']}, limit={v['limit']}\")
if not d['passed']:
    exit(1)
"
    if errorlevel 1 set OVERALL_PASS=1
) else (
    REM Evaluate all active policies
    curl -sf %AUTH_FLAG% "%API_URL%/api/v1/policies/?active_only=true" -o "%TEMP%\argus_policies.json"
    if errorlevel 1 (
        echo ERROR: Failed to fetch active policies
        exit /b 2
    )
    python -c "
import json, subprocess, sys, os, tempfile

policies = json.load(open(r'%TEMP%\argus_policies.json'))
scan_id = '%SCAN_ID%'
api_url = '%API_URL%'
api_key = '%API_KEY%'
auth = ['-H', f'Authorization: Bearer {api_key}'] if api_key else []
overall = 0

if not policies:
    print('No active policies - scan passes by default.')
    sys.exit(0)

print('Policy evaluations:')
for p in policies:
    out_file = tempfile.mktemp(suffix='.json')
    r = subprocess.run(
        ['curl', '-sf'] + auth + ['-X', 'POST',
         f'{api_url}/api/v1/policies/{p[\"id\"]}/evaluate/{scan_id}',
         '-o', out_file],
        capture_output=True
    )
    if r.returncode != 0:
        print(f'  [ERROR] {p[\"name\"]}')
        overall = 1
        continue
    d = json.load(open(out_file))
    status = 'PASS' if d['passed'] else 'FAIL'
    print(f'  [{status}] {d[\"policy_name\"]}')
    for v in d.get('violations', []):
        print(f'    - {v[\"rule\"]}: actual={v[\"actual\"]}, limit={v[\"limit\"]}')
    if not d['passed']:
        overall = 1

sys.exit(overall)
"
    if errorlevel 1 set OVERALL_PASS=1
)

echo.
if %OVERALL_PASS%==0 (
    echo RESULT: PASSED
) else (
    echo RESULT: FAILED - scan did not meet policy requirements
)

exit /b %OVERALL_PASS%
