@echo off
setlocal EnableDelayedExpansion
:: ============================================================================
:: ConFireTV - Windows Service Installer (NSSM)
:: Run as Administrator: Right-click -> "Run as administrator"
::
:: Prerequisites:
::   1. Python 3.9+ installed and in PATH
::   2. NSSM installed -> https://nssm.cc/download
::      (extract nssm.exe to C:\Windows\System32)
::   3. Android Platform Tools (adb.exe) in PATH
::      -> https://developer.android.com/studio/releases/platform-tools
::   4. venv created:  python -m venv venv
::      deps installed: venv\Scripts\pip install -r requirements.txt
:: ============================================================================

:: Resolve project root (two levels up from platform\windows\)
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\.."
set "PROJECT_DIR=%CD%"
popd

set "VENV_PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe"
set "VENV_UVICORN=%PROJECT_DIR%\venv\Scripts\uvicorn.exe"
set "LOGS_DIR=%PROJECT_DIR%\logs"

echo.
echo  ConFireTV - Windows Service Installer
echo  =========================================
echo  Project: %PROJECT_DIR%
echo.

:: --- 1. Admin check ---
net session >nul 2>&1
if not %errorlevel% == 0 (
    echo  [ERROR] This script must be run as Administrator.
    echo          Right-click install_service.bat and choose "Run as administrator"
    pause
    exit /b 1
)
echo  [OK] Running as Administrator

:: --- 2. Check NSSM ---
where nssm >nul 2>&1
if not %errorlevel% == 0 (
    echo.
    echo  [ERROR] NSSM not found in PATH.
    echo.
    echo  NSSM is a free Windows service manager (not a Python package).
    echo  Install it in 3 steps:
    echo.
    echo    1. Download from: https://nssm.cc/download
    echo       (click the top link, e.g. nssm-2.24.zip)
    echo.
    echo    2. Extract the zip. Open the win64 folder inside.
    echo.
    echo    3. Copy nssm.exe to: C:\Windows\System32\
    echo.
    echo  Then open a NEW Administrator Command Prompt and run this script again.
    pause
    exit /b 1
)
echo  [OK] NSSM found

:: --- 3. Check Python venv ---
if not exist "%VENV_PYTHON%" (
    echo.
    echo  [ERROR] venv not found at: %VENV_PYTHON%
    echo.
    echo  Create it by running in the project folder:
    echo    python -m venv venv
    echo    venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo  [OK] Python venv: %VENV_PYTHON%

:: --- 4. Check config.yaml ---
if not exist "%PROJECT_DIR%\config.yaml" (
    echo.
    echo  [ERROR] config.yaml not found.
    echo  Copy config.yaml.example to config.yaml and fill in your settings.
    pause
    exit /b 1
)
echo  [OK] config.yaml found

:: --- 5. Locate adb.exe ---
set "ADB_BIN="
for %%A in (adb.exe) do set "ADB_BIN=%%~$PATH:A"

if "!ADB_BIN!"=="" (
    if exist "C:\platform-tools\adb.exe" set "ADB_BIN=C:\platform-tools\adb.exe"
)
if "!ADB_BIN!"=="" (
    if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
        set "ADB_BIN=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
    )
)

if "!ADB_BIN!"=="" (
    echo.
    echo  [ERROR] adb.exe not found.
    echo.
    echo  Download Android Platform Tools from:
    echo    https://developer.android.com/studio/releases/platform-tools
    echo.
    echo  Extract the zip to C:\platform-tools\
    echo  Then add C:\platform-tools to your system PATH.
    pause
    exit /b 1
)

for %%F in ("!ADB_BIN!") do set "ADB_DIR=%%~dpF"
if "!ADB_DIR:~-1!"=="\" set "ADB_DIR=!ADB_DIR:~0,-1!"
echo  [OK] adb.exe found: !ADB_BIN!

:: --- 6. Create logs directory ---
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"
echo  [OK] Logs directory: %LOGS_DIR%

:: --- 7. Windows Firewall - allow port 8000 inbound ---
echo.
echo  Configuring Windows Firewall for port 8000...
netsh advfirewall firewall delete rule name="ConFireTV Dashboard" >nul 2>&1
netsh advfirewall firewall add rule name="ConFireTV Dashboard" dir=in action=allow protocol=TCP localport=8000 >nul
echo  [OK] Firewall rule added - dashboard reachable from other devices on WiFi

:: --- 8. Remove old services if they exist ---
echo.
echo  Removing any existing ConFireTV services...
for %%S in (ConFireTV-Poller ConFireTV-Web ConFireTV-Scheduler) do (
    nssm status %%S >nul 2>&1
    if !errorlevel! == 0 (
        nssm stop %%S >nul 2>&1
        nssm remove %%S confirm >nul 2>&1
        echo  [REMOVED] %%S
    )
)

:: --- 9. Install services ---
echo.
echo  Installing services...

nssm install ConFireTV-Poller "%VENV_PYTHON%"
nssm set ConFireTV-Poller AppParameters "-m monitor.adb_poller"
nssm set ConFireTV-Poller AppDirectory "%PROJECT_DIR%"
nssm set ConFireTV-Poller DisplayName "ConFireTV Monitor (ADB Poller)"
nssm set ConFireTV-Poller Description "Monitors Amazon Fire TV Stick via ADB."
nssm set ConFireTV-Poller Start SERVICE_AUTO_START
nssm set ConFireTV-Poller AppStdout "%LOGS_DIR%\poller.log"
nssm set ConFireTV-Poller AppStderr "%LOGS_DIR%\poller.log"
nssm set ConFireTV-Poller AppRotateFiles 1
nssm set ConFireTV-Poller AppRotateBytes 5242880
nssm set ConFireTV-Poller AppRestartDelay 10000
nssm set ConFireTV-Poller AppEnvironmentExtra "PATH=!ADB_DIR!;%SystemRoot%\System32;%SystemRoot%"
echo  [OK] ConFireTV-Poller installed

nssm install ConFireTV-Web "%VENV_UVICORN%"
nssm set ConFireTV-Web AppParameters "web.app:app --host 0.0.0.0 --port 8000"
nssm set ConFireTV-Web AppDirectory "%PROJECT_DIR%"
nssm set ConFireTV-Web DisplayName "ConFireTV Dashboard (Web Server)"
nssm set ConFireTV-Web Description "Web dashboard for ConFireTV. Access at http://localhost:8000"
nssm set ConFireTV-Web Start SERVICE_AUTO_START
nssm set ConFireTV-Web AppStdout "%LOGS_DIR%\web.log"
nssm set ConFireTV-Web AppStderr "%LOGS_DIR%\web.log"
nssm set ConFireTV-Web AppRotateFiles 1
nssm set ConFireTV-Web AppRotateBytes 5242880
nssm set ConFireTV-Web AppRestartDelay 5000
echo  [OK] ConFireTV-Web installed

nssm install ConFireTV-Scheduler "%VENV_PYTHON%"
nssm set ConFireTV-Scheduler AppParameters "scheduler.py"
nssm set ConFireTV-Scheduler AppDirectory "%PROJECT_DIR%"
nssm set ConFireTV-Scheduler DisplayName "ConFireTV Scheduler (Reports and Bedtime)"
nssm set ConFireTV-Scheduler Description "Sends daily reports and enforces bedtime on Fire TV."
nssm set ConFireTV-Scheduler Start SERVICE_AUTO_START
nssm set ConFireTV-Scheduler AppStdout "%LOGS_DIR%\scheduler.log"
nssm set ConFireTV-Scheduler AppStderr "%LOGS_DIR%\scheduler.log"
nssm set ConFireTV-Scheduler AppRotateFiles 1
nssm set ConFireTV-Scheduler AppRotateBytes 5242880
nssm set ConFireTV-Scheduler AppRestartDelay 10000
echo  [OK] ConFireTV-Scheduler installed

:: --- 10. Start services ---
echo.
echo  Starting services...

nssm start ConFireTV-Poller
if %errorlevel% == 0 (
    echo  [STARTED] ConFireTV-Poller
) else (
    echo  [WARN] ConFireTV-Poller did not start - check logs
)

nssm start ConFireTV-Web
if %errorlevel% == 0 (
    echo  [STARTED] ConFireTV-Web
) else (
    echo  [WARN] ConFireTV-Web did not start - check logs
)

nssm start ConFireTV-Scheduler
if %errorlevel% == 0 (
    echo  [STARTED] ConFireTV-Scheduler
) else (
    echo  [WARN] ConFireTV-Scheduler did not start - check logs
)

:: --- 11. Summary ---
echo.
echo  =========================================
echo  Installation complete!
echo.
echo  Dashboard (this PC):      http://localhost:8000

for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /i "IPv4"') do (
    set "WIFI_IP=%%A"
    set "WIFI_IP=!WIFI_IP: =!"
    if not "!WIFI_IP!"=="127.0.0.1" (
        echo  Dashboard (other devices):  http://!WIFI_IP!:8000
    )
)

echo.
echo  Manage services:  platform\windows\manage.bat status
echo  View live logs:   platform\windows\manage.bat logs
echo  Stop all:         platform\windows\manage.bat stop
echo.
echo  Services start automatically at every Windows boot.
echo  =========================================
echo.
pause
