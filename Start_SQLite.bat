@echo off
rem ---------------------------------------------------------------------------
rem  SQLite launcher for THIS client.
rem
rem  This PC has a machine-wide DATABASE_URL that points at another client's
rem  PostgreSQL database. While it is set, this app silently connects to that
rem  Postgres and ignores database\inventory.db. Clearing it here keeps this
rem  client on its own local SQLite file.
rem ---------------------------------------------------------------------------
setlocal
set "DATABASE_URL="

cd /d "%~dp0"

set "PY=%~dp0build_env\Scripts\python.exe"

if exist "%PY%" (
    start "" "%PY%" "%~dp0main.py"
    exit /b 0
)

if exist "%~dp0dist\InventoryManager.exe" (
    start "" "%~dp0dist\InventoryManager.exe"
    exit /b 0
)

echo Could not find build_env\Scripts\python.exe or dist\InventoryManager.exe.
pause
