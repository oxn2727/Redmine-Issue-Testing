@echo off
setlocal EnableExtensions
title Redmine Test Environment Launcher

rem ============================================================
rem  Redmine local test environment - one click launcher
rem  Put this file in the same folder as docker-compose.yml
rem  Steps: check docker -> make sure engine runs -> compose up
rem ============================================================

set "DD_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
set "MAXWAIT=180"
set "URL=http://localhost:3000"

cd /d "%~dp0"

echo ============================================================
echo   Redmine test environment launcher
echo ============================================================
echo.

rem ---------- step 0: docker CLI present? ----------
where docker >nul 2>nul
if errorlevel 1 (
    echo [ERROR] "docker" command not found in PATH.
    echo         Install Docker Desktop, then open a NEW terminal.
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('docker --version 2^>nul') do echo [OK] %%v
echo.

rem ---------- step 1: is the engine already up? ----------
echo [1/4] Checking Docker engine ...
docker info >nul 2>nul
if not errorlevel 1 goto :ENGINE_OK

echo       Engine is NOT running - Docker Desktop is not started.
echo.

if exist "%DD_EXE%" (
    echo       Starting Docker Desktop ...
    start "" "%DD_EXE%"
) else (
    echo       [WARN] Not found: "%DD_EXE%"
    echo       Please start Docker Desktop from the Start menu.
)
echo       First start may take 1-3 minutes. Waiting ...
echo.

set /a WAITED=0
:WAIT_ENGINE
timeout /t 5 /nobreak >nul
set /a WAITED+=5
docker info >nul 2>nul
if not errorlevel 1 goto :ENGINE_OK
echo       ... waiting for engine  ^( %WAITED%s / %MAXWAIT%s ^)
if %WAITED% LSS %MAXWAIT% goto :WAIT_ENGINE

echo.
echo [FAIL] Engine did not start within %MAXWAIT%s.
echo        Do these in order:
echo          1^) Open Docker Desktop, read the error text on screen
echo          2^) Run:  wsl --update      ^(in an admin terminal^)
echo          3^) Sign out of Windows and sign in again, then retry
echo.
pause
exit /b 1

:ENGINE_OK
echo       OK - Docker engine is running.
echo.

rem ---------- step 2: build and start containers ----------
echo [2/4] Pulling images and starting containers ...
echo       (first run downloads mysql + redmine, may take a while)
echo.
docker compose up -d
if errorlevel 1 (
    echo.
    echo [FAIL] "docker compose up -d" failed. Read the error above.
    echo        - proxy / registry timeout  -^>  check your proxy setting
    echo        - port already in use       -^>  change 3000:3000 in yml
    echo.
    pause
    exit /b 1
)

echo.
echo [3/4] Waiting for Redmine web UI on %URL% ...
set /a WAITED=0
:WAIT_WEB
timeout /t 5 /nobreak >nul
set /a WAITED+=5
curl -s -o nul --max-time 3 %URL%
if not errorlevel 1 goto :WEB_OK
echo       ... Redmine is still booting  ^( %WAITED%s / 180s ^)
if %WAITED% LSS 180 goto :WAIT_WEB
echo       [WARN] Timed out waiting for the web UI, but containers may
echo              still be starting. Check:  docker compose logs -f redmine
echo.

:WEB_OK
echo.
echo [3.5/4] Checking Redmine default data (trackers) ...
set "TRK="
for /f "delims=" %%n in ('docker exec redmin_test-db-1 mysql --default-character-set=utf8mb4 -uredmine -predmine123 redmine -N -B -e "select name from trackers;" 2^>nul') do set "TRK=1"
if defined TRK (
    echo       OK - trackers are loaded, workflow page will work.
) else (
    echo       [WARN] Cannot read trackers from the database.
    echo              Either the db container is not up yet, or the Redmine
    echo              DEFAULT DATA was never loaded ^(very common on a fresh db^).
    echo              Symptom: the "Edit" button on  Administration - Workflow
    echo                       does nothing, and the Tracker dropdown is empty.
    echo              Fix: run seed-default-data.rb, seed-workflow.rb and
    echo                   seed-roles.rb from this folder
    echo                   ^(see the doc, chapters 1, 4 and 5^).
)

echo.
echo [3.6/4] Checking role permissions ...
docker exec redmin_test-db-1 mysql --default-character-set=utf8mb4 -uredmine -predmine123 redmine -N -B -e "select r.name, length(r.permissions)-length(replace(r.permissions,'- :','')) from roles r where r.builtin=0 and r.name in ('Reporter','Developer','Manager');" 2>nul
echo       Expected:  Reporter 20 / Developer 31 / Manager 76
echo       Wrong numbers -^> run seed-roles.rb  ^(doc chapter 4^)

echo.
echo [3.7/4] Checking test accounts can log in ...
docker exec redmin_test-redmine-1 sh -c "cd /usr/src/redmine && export SECRET_KEY_BASE=\"$REDMINE_SECRET_KEY_BASE\" && RAILS_ENV=production bundle exec rails runner \"%w[admin reporter1 developer1 manager1].each{|l| u=User.find_by(login: l); puts (u.nil? ? \\\"#{l} MISSING\\\" : \\\"#{l} status=#{u.status} pw_ok=#{u.check_password?('Test@1234')}\\\")}\"" 2>nul
echo       Expected: admin / reporter1 / developer1 / manager1  pw_ok=true
echo       Any false or MISSING  -^> run reset-passwords.cmd  (doc chapter 8.1)

echo.
echo [4/4] Ready.
echo.
echo   Open in browser : %URL%
echo   Test accounts   : admin / reporter1 / developer1 / manager1
echo                     password: Test@1234
echo   UI language     : English  ^(do NOT switch to Chinese - it breaks
echo                     the 18 API assertions that compare English names^)
echo.
echo   Useful commands:
echo     docker compose ps            show container status
echo     docker compose logs -f       follow logs
echo     docker compose stop          stop containers (keep data)
echo     docker compose down          remove containers (keep ./mysql-data)
echo.
pause
exit /b 0
