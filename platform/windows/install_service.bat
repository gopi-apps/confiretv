@echo off
setlocal EnableDelayedExpansion
:: ============================================================================
:: ConFireTV — Windows Service Installer (NSSM)
:: Run as Administrator: Right-click → "Run as administrator"
::
:: Prerequisites:
::   1. Python 3.9+ installed and in PATH
::   2. NSSM installed and in PATH  →  https://nssm.cc/download
::      (download nssm.exe, place in C:\Windows\System32 or any PATH folder)
::   3. Android Platform Tools (adb.exe) in PATH
::      →  https://developer.android.com/studio/releases/platform-tools
::   4. venv created:  python -m venv venv
::      deps installed: venv\Scripts\pip install -r requirements.txt
:: ============================================================================

:: Resolve project root (two levels up from platform\windows\)
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\..\"
set "PROJECT_DIR=%CD%"
popd

set "VENV_PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe"
set "VENV_UVICORN=%PROJECT_DIR%\venv\Scripts\uvicorn.exe"
set "LOGS_DIR=%PROJECT_DIR%\logs"

echo.
echo  ConFireTV -- Windows Service Installer
echo  =========================================
echo  Project: %PROJECT_DIR%
echo.

:: ── 1. Admin check ───────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] This script must be run as Administrator.
    echo          Right-click install_service.bat and choose "Run as administrator"
    pause
    exit /b 1
)
echo  [OK] Running as Administrator

:: ── 2. Check NSSM ────────────────────────────────────────────────────────────
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] nssm not found in PATH.
    echo.
    echo  Download NSSM from https://nssm.cc/download
    echo  Extract nssm.exe and place it in C:\Windows\System32
    echo  Then run this script again.
    pause
    exit /b 1
)
echo  [OK] NSSM found

:: ── 3. Check Python venv ─────────────────────────────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo.
    echo  [ERROR] venv not found at %VENV_PYTHON%
    echo.
    echo  Create it by running in the project folder:
    echo    python -m venv venv
    echo    venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo  [OK] Python venv: %VENV_PYTHON%

:: ── 4. Check config.yaml ─────────────────────────────────────────────────────
if not exist "%PROJECT_DIR%\config.yaml" (
    echo.
    echo  [ERROR] config.yaml not found.
    echo  Copy config.yaml.example to config.yaml and fill in your settings.
    pause
    exit /b 1
)
echo  [OK] config.yaml found

:: ── 5. Create logs directory ─────────────────────────────────────────────────
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"
echo  [OK] Logs directory: %LOGS_DIR%

:: ── 6. Stop and remove old services if they exist ────────────────────────────
echo.
echo  Removing any existing ConFireTV services...
for %%S in (ConFireTV-Poller ConFireTV-Web ConFireTV-Scheduler) do (
    nssm status %%S >nul 2>&1
    if !errorlevel! equ 0 (
        nssm stop %%S >nul 2>&1
        nssm remove %%S confirm >nul 2>&1
        echo  [REMOVED] %%S
    )
)

:: ── 7. Install services ──────────────────────────────────────────────────────
echo.
echo  Installing services...

:: --- Poller ------------------------------------------------------------------
nssm install ConFireTV-Poller "%VENV_PYTHON%"
nssm set ConFireTV-Poller AppParameters "-m monitor.adb_poller"
nssm set ConFireTV-Poller AppDirectory "%PROJECT_DIR%"
nssm set ConFireTV-Poller DisplayName "ConFireTV Monitor (ADB Poller)"
nssm set ConFireTV-Poller Description "Monitors Amazon Fire TV Stick via ADB. Part of ConFireTV parental controls."
nssm set ConFireTV-Poller Start SERVICE_AUTO_START
nssm set ConFireTV-Poller AppStdout "%LOGS_DIR%\poller.log"
nssm set ConFireTV-Poller AppStderr "%LOGS_DIR%\poller.log"
nssm set ConFireTV-Poller AppRotateFiles 1
nssm set ConFireTV-Poller AppRotateBytes 5242880
nssm set ConFireTV-Poller AppRestartDelay 10000
echo  [OK] ConFireTV-Poller installed

:: --- Web ---------------------------------------------------------------------
nssm install ConFireTV-Web "%VENV_UVICORN%"
nssm set ConFireTV-Web AppParameters "web.app:app --host 0.0.0.0 --port 8000"
nssm set ConFireTV-Web AppDirectory "%PROJECT_DIR%"
nssm set ConFireTV-Web DisplayName "ConFireTV Dashboard (Web Server)"
nssm set ConFireTV-Web Description "Web dashboard for ConFireTV parental controls. Access at http://localhost:8000"
nssm set ConFireTV-Web Start SERVICE_AUTO_START
nssm set ConFireTV-Web AppStdout "%LOGS_DIR%\web.log"
nssm set ConFireTV-Web AppStderr "%LOGS_DIR%\web.log"
nssm set ConFireTV-Web AppRotateFiles 1
nssm set ConFireTV-Web AppRotateBytes 5242880
nssm set ConFireTV-Web AppRestartDelay 5000
echo  [OK] ConFireTV-Web installed

:: --- Scheduler ---------------------------------------------------------------
nssm install ConFireTV-Scheduler "%VENV_PYTHON%"
nssm set ConFireTV-Scheduler AppParameters "scheduler.py"
nssm set ConFireTV-Scheduler AppDirectory "%PROJECT_DIR%"
nssm set ConFireTV-Scheduler DisplayName "ConFireTV Scheduler (Reports & Bedtime)"
nssm set ConFireTV-Scheduler Description "Sends daily reports and enforces bedtime on Fire TV. Part of ConFireTV."
nssm set ConFireTV-Scheduler Start SERVICE_AUTO_START
nssm set ConFireTV-Scheduler AppStdout "%LOGS_DIR%\scheduler.log"
nssm set ConFireTV-Scheduler AppStderr "%LOGS_DIR%\scheduler.log"
nssm set ConFireTV-Scheduler AppRotateFiles 1
nssm set ConFireTV-Scheduler AppRotateBytes 5242880
nssm set ConFireTV-Scheduler AppRestartDelay 10000
echo  [OK] ConFireTV-Scheduler installed

:: ── 8. Start services ────────────────────────────────────────────────────────
echo.
echo  Starting services...
nssm start ConFireTV-Poller    && echo  [STARTED] ConFireTV-Poller    || echo  [WARN] ConFireTV-Poller may have failed — check logs
nssm start ConFireTV-Web       && echo  [STARTED] ConFireTV-Web       || echo  [WARN] ConFireTV-Web may have failed — check logs
nssm start ConFireTV-Scheduler && echo  [STARTED] ConFireTV-Scheduler || echo  [WARN] ConFireTV-Scheduler may have failed — check logs

:: ── 9. Summary ───────────────────────────────────────────────────────────────
echo.
echo  =========================================
echo  Installation complete!
echo.
echo  Dashboard:    http://localhost:8000
echo               (or http://THIS-PC-IP:8000 from any device on WiFi)
echo.
echo  Manage:       platform\windows\manage.bat status
echo  View logs:    platform\windows\manage.bat logs
echo  Stop all:     platform\windows\manage.bat stop
echo.
echo  Services start automatically at Windows boot.
echo  =========================================
echo.
pause
