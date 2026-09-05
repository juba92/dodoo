@echo off
setlocal enabledelayedexpansion
title Dodoo - prepare and start
cd /d "%~dp0"

REM ============================================================================
REM  One-click: install deps, provision a local PostgreSQL, install the
REM  localization module, and start the Dodoo web app at http://127.0.0.1:8069
REM ============================================================================

set "PGPORT=55432"
set "PGDB=dodoo"
set "APPPORT=8069"
set "PGDATA=%LOCALAPPDATA%\dodoo-dev-pg\data"
set "PGLOG=%LOCALAPPDATA%\dodoo-dev-pg\server.log"
set "PGBIN="

REM Reuse an existing portable PostgreSQL if one is already unpacked.
if exist "%USERPROFILE%\dpg\pgsql\bin\postgres.exe" set "PGBIN=%USERPROFILE%\dpg\pgsql\bin"
if not defined PGBIN if exist "%LOCALAPPDATA%\dodoo-dev-pg\pgsql\bin\postgres.exe" set "PGBIN=%LOCALAPPDATA%\dodoo-dev-pg\pgsql\bin"

REM Locate Python 3.
set "PY=py -3"
%PY% --version >nul 2>&1 || set "PY=python"
%PY% --version >nul 2>&1 || (echo [ERROR] Python 3 was not found on PATH. & pause & exit /b 1)

echo.
echo === [1/6] Python dependencies ===
%PY% -c "import sqlalchemy, fastapi, asyncpg, argon2, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo Installing project + dev dependencies ^(one time^)...
  %PY% -m pip install -e ".[dev]" || (echo [ERROR] pip install failed. & pause & exit /b 1)
) else (
  echo Already installed.
)

echo.
echo === [2/6] PostgreSQL binaries ===
if not defined PGBIN (
  echo Downloading PostgreSQL 16 portable binaries ^(~340 MB, one time^)...
  if not exist "%LOCALAPPDATA%\dodoo-dev-pg" mkdir "%LOCALAPPDATA%\dodoo-dev-pg"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $z=Join-Path $env:LOCALAPPDATA 'dodoo-dev-pg\pg.zip'; if (-not (Test-Path $z)) { Invoke-WebRequest 'https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip' -OutFile $z }; Expand-Archive -Path $z -DestinationPath (Join-Path $env:LOCALAPPDATA 'dodoo-dev-pg') -Force"
  if errorlevel 1 (echo [ERROR] PostgreSQL download/extract failed. & pause & exit /b 1)
  set "PGBIN=%LOCALAPPDATA%\dodoo-dev-pg\pgsql\bin"
)
echo Using: %PGBIN%

echo.
echo === [3/6] PostgreSQL cluster ===
if not exist "%PGDATA%\PG_VERSION" (
  echo Initializing data directory...
  "%PGBIN%\initdb" -D "%PGDATA%" -U postgres --auth=trust -E UTF8 --no-locale || (echo [ERROR] initdb failed. & pause & exit /b 1)
)
"%PGBIN%\pg_isready" -h 127.0.0.1 -p %PGPORT% >nul 2>&1
if errorlevel 1 (
  echo Starting PostgreSQL on port %PGPORT%...
  "%PGBIN%\pg_ctl" -D "%PGDATA%" -o "-p %PGPORT% -c listen_addresses=127.0.0.1 -c fsync=off" -l "%PGLOG%" -w -t 30 start
  if errorlevel 1 (echo [ERROR] pg_ctl start failed - see %PGLOG% & pause & exit /b 1)
) else (
  echo Already running on port %PGPORT%.
)

echo.
echo === [4/6] Database "%PGDB%" ===
"%PGBIN%\psql" -h 127.0.0.1 -p %PGPORT% -U postgres -Atqc "SELECT 1 FROM pg_database WHERE datname='%PGDB%'" | findstr "1" >nul
if errorlevel 1 (
  "%PGBIN%\psql" -h 127.0.0.1 -p %PGPORT% -U postgres -c "CREATE DATABASE %PGDB%" || (echo [ERROR] CREATE DATABASE failed. & pause & exit /b 1)
) else (
  echo Exists.
)

set "DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:%PGPORT%/%PGDB%"
set "DATABASE_MIGRATION_URL=%DATABASE_URL%"
set "SESSION_EXPIRY_HOURS=8"

echo.
echo === [5/6] Install / update the localization module ===
echo ^(pulls in base, account, web; seeds Arabic + Egypt on a fresh database^)
%PY% -m dodoo module install localization || (echo [ERROR] module install failed. & pause & exit /b 1)

echo.
echo === [6/6] Start the web app ===
echo Opening http://127.0.0.1:%APPPORT%/web/client  ^(login: admin / admin^)
start "" "http://127.0.0.1:%APPPORT%/web/client"
echo.
echo Server logs follow. Press Ctrl+C in this window to stop the app.
echo.
%PY% -m dodoo server --host 127.0.0.1 --port %APPPORT%

echo.
echo Web app stopped. PostgreSQL is still running in the background.
echo To stop it:  "%PGBIN%\pg_ctl" -D "%PGDATA%" stop
echo.
pause
