@echo off
REM Export the Argus OpenAPI 3.1 schema and optionally regenerate the TypeScript client.
REM
REM Usage:
REM   scripts\export-openapi.bat              -- export JSON only
REM   scripts\export-openapi.bat --gen-client -- export + regenerate TS client

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
set "SCHEMA_OUT=%REPO_ROOT%\surfaces\dashboard\src\api\openapi.json"
set "GEN_CLIENT=false"

:parse_args
if "%~1"=="" goto :done_parse
if /I "%~1"=="--gen-client" set "GEN_CLIENT=true"
shift
goto :parse_args
:done_parse

echo Exporting OpenAPI schema...
cd /d "%REPO_ROOT%"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python -c ^
"import json, sys; sys.path.insert(0, '.'); from core.api.app import create_app; app = create_app(); schema = app.openapi(); f = open('surfaces/dashboard/src/api/openapi.json', 'w'); json.dump(schema, f, indent=2); f.write('\n'); f.close(); print(f'Schema written to surfaces/dashboard/src/api/openapi.json ({len(schema.get(\"paths\", {}))} paths)')"

if errorlevel 1 (
    echo ERROR: Failed to export schema.
    exit /b 1
)

if "%GEN_CLIENT%"=="true" (
    echo Regenerating TypeScript client...
    cd /d "%REPO_ROOT%\surfaces\dashboard"
    where npx >nul 2>&1
    if errorlevel 1 (
        echo npx not found -- install Node.js to regenerate the TypeScript client
        exit /b 1
    )
    npx openapi-typescript ..\..\..\surfaces\dashboard\src\api\openapi.json ^
        --output src\api\schema.d.ts
    echo TypeScript types written to surfaces\dashboard\src\api\schema.d.ts
)

echo Done.
endlocal
