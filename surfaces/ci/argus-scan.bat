@echo off
:: surfaces/ci/argus-scan.bat
::
:: Trigger an Argus security scan and gate on severity.
::
:: Required env vars:
::   ARGUS_API_BASE   - e.g. http://localhost:8000  (default: http://localhost:8000)
::   ARGUS_TARGET     - target_ref for the scan (required)
::
:: Optional env vars:
::   ARGUS_MODE           - at_rest | real_time  (default: at_rest)
::   ARGUS_APPROACH       - security approach    (default: penetration_testing)
::   ARGUS_PIPELINE       - pipeline config name (default: full-scan)
::   ARGUS_FAIL_ON        - comma-separated severities (default: critical,high)
::   ARGUS_TIMEOUT_SEC    - polling timeout in seconds (default: 600)
::   ARGUS_POLL_INTERVAL  - seconds between status checks (default: 10)

setlocal enabledelayedexpansion

if not defined ARGUS_API_BASE set "ARGUS_API_BASE=http://localhost:8000"
if not defined ARGUS_TARGET (
    echo ERROR: ARGUS_TARGET is required >&2
    exit /b 1
)
if not defined ARGUS_MODE set "ARGUS_MODE=at_rest"
if not defined ARGUS_APPROACH set "ARGUS_APPROACH=penetration_testing"
if not defined ARGUS_PIPELINE set "ARGUS_PIPELINE=full-scan"
if not defined ARGUS_FAIL_ON set "ARGUS_FAIL_ON=critical,high"
if not defined ARGUS_TIMEOUT_SEC set "ARGUS_TIMEOUT_SEC=600"
if not defined ARGUS_POLL_INTERVAL set "ARGUS_POLL_INTERVAL=10"

where curl >nul 2>&1 || (echo ERROR: curl is required but not found in PATH >&2 && exit /b 1)
where jq >nul 2>&1   || (echo ERROR: jq is required but not found in PATH >&2 && exit /b 1)

echo === Argus Security Scan ===
echo   Target:   %ARGUS_TARGET%
echo   Mode:     %ARGUS_MODE%
echo   Approach: %ARGUS_APPROACH%
echo   Pipeline: %ARGUS_PIPELINE%
echo   Fail on:  %ARGUS_FAIL_ON%
echo.

:: Trigger scan
set "BODY={\"target_ref\":\"%ARGUS_TARGET%\",\"mode\":\"%ARGUS_MODE%\",\"approach\":\"%ARGUS_APPROACH%\",\"pipeline_config_name\":\"%ARGUS_PIPELINE%\"}"

for /f "delims=" %%i in ('curl --silent --fail --show-error -X POST "%ARGUS_API_BASE%/api/v1/scans/" -H "Content-Type: application/json" -d "%BODY%"') do set "TRIGGER_RESP=%%i"
for /f "delims=" %%i in ('echo !TRIGGER_RESP! ^| jq -r ".scan_id"') do set "SCAN_ID=%%i"
echo Scan started: %SCAN_ID%
echo.

:: Poll for completion
set /a ELAPSED=0

:poll_loop
for /f "delims=" %%i in ('curl --silent --fail --show-error "%ARGUS_API_BASE%/api/v1/scans/%SCAN_ID%"') do set "STATUS_RESP=%%i"
for /f "delims=" %%i in ('echo !STATUS_RESP! ^| jq -r ".status"') do set "STATUS=%%i"
echo [%ELAPSED%s] Scan status: %STATUS%

if "%STATUS%"=="completed" goto scan_done
if "%STATUS%"=="failed" (
    echo ERROR: Scan failed >&2
    exit /b 2
)
if "%STATUS%"=="cancelled" (
    echo ERROR: Scan was cancelled >&2
    exit /b 2
)

if %ELAPSED% geq %ARGUS_TIMEOUT_SEC% (
    echo ERROR: Timed out waiting for scan to complete after %ARGUS_TIMEOUT_SEC%s >&2
    exit /b 2
)

timeout /t %ARGUS_POLL_INTERVAL% >nul
set /a ELAPSED=%ELAPSED%+%ARGUS_POLL_INTERVAL%
goto poll_loop

:scan_done
echo.
echo === Findings Summary ===

for /f "delims=" %%i in ('curl --silent --fail --show-error "%ARGUS_API_BASE%/api/v1/scans/%SCAN_ID%/findings"') do set "FINDINGS_RESP=%%i"
for /f "delims=" %%i in ('echo !FINDINGS_RESP! ^| jq "length"') do set "TOTAL=%%i"
echo Total findings: %TOTAL%
echo.

for %%s in (critical high medium low info) do (
    for /f "delims=" %%n in ('echo !FINDINGS_RESP! ^| jq "[.[] | select(.severity == \"%%s\")] | length"') do (
        echo   %%s    %%n
    )
)
echo.

:: Gate on severity
set /a FAIL=0
for %%s in (%ARGUS_FAIL_ON:,= %) do (
    for /f "delims=" %%n in ('echo !FINDINGS_RESP! ^| jq "[.[] | select(.severity == \"%%s\" and .status != \"dismissed\")] | length"') do (
        if %%n gtr 0 (
            echo GATE FAILED: %%n %%s finding^(s^) found >&2
            set /a FAIL=1
        )
    )
)

if %FAIL%==1 (
    echo.>&2
    echo Scan gate failed — see findings above. >&2
    exit /b 1
)

echo Scan gate passed.
endlocal
