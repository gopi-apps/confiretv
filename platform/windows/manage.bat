@echo off
setlocal EnableDelayedExpansion
:: ============================================================================
:: ConFireTV — Windows Service Manager
:: Usage (run as Administrator):
::   manage.bat status
::   manage.bat start
::   manage.bat stop
::   manage.bat restart
::   manage.bat logs              (tail all logs)
::   manage.bat logs poller|web|scheduler
:: ============================================================================

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\..\"
set "PROJECT_DIR=%CD%"
popd
set "LOGS_DIR=%PROJECT_DIR%\logs"
set "CMD=%~1"
set "ARG=%~2"

if "%CMD%"=="" set "CMD=status"

if /i "%CMD%"=="status"  goto do_status
if /i "%CMD%"=="start"   goto do_start
if /i "%CMD%"=="stop"    goto do_stop
if /i "%CMD%"=="restart" goto do_restart
if /i "%CMD%"=="logs"    goto do_logs

echo Usage: manage.bat [status^|start^|stop^|restart^|logs [poller^|web^|scheduler]]
exit /b 1

:: ── STATUS ──────────────────────────────────────────────────────────────────
:do_status
echo.
echo  ConFireTV Service Status
echo  ─────────────────────────────────────────
for %%S in (Poller Web Scheduler) do (
    set "SVC=ConFireTV-%%S"
    sc query !SVC! >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=4" %%A in ('sc query !SVC! ^| findstr "STATE"') do (
            if "%%A"=="RUNNING" (
                echo  [RUNNING]  ConFireTV-%%S
            ) else (
                echo  [STOPPED]  ConFireTV-%%S  (state: %%A)
            )
        )
    ) else (
        echo  [NOT INSTALLED]  ConFireTV-%%S
    )
)
echo.
echo  Dashboard:  http://localhost:8000
echo  Logs dir:   %LOGS_DIR%
echo.
goto end

:: ── START ────────────────────────────────────────────────────────────────────
:do_start
echo.
echo  Starting ConFireTV services...
for %%S in (Poller Web Scheduler) do (
    nssm start ConFireTV-%%S >nul 2>&1
    echo  [START] ConFireTV-%%S
)
timeout /t 3 /nobreak >nul
goto do_status

:: ── STOP ─────────────────────────────────────────────────────────────────────
:do_stop
echo.
echo  Stopping ConFireTV services...
for %%S in (Scheduler Web Poller) do (
    nssm stop ConFireTV-%%S >nul 2>&1
    echo  [STOP] ConFireTV-%%S
)
echo  Done.
goto end

:: ── RESTART ──────────────────────────────────────────────────────────────────
:do_restart
call :do_stop
timeout /t 3 /nobreak >nul
call :do_start
goto end

:: ── LOGS ─────────────────────────────────────────────────────────────────────
:do_logs
if not exist "%LOGS_DIR%" (
    echo  No logs directory found at %LOGS_DIR%
    goto end
)

if not "%ARG%"=="" (
    set "LOGFILE=%LOGS_DIR%\%ARG%.log"
    if not exist "!LOGFILE!" (
        echo  Log file not found: !LOGFILE!
        goto end
    )
    echo  Showing last 50 lines of %ARG%.log  (Ctrl+C to stop)
    echo  ────────────────────────────────────────────────────
    powershell -Command "Get-Content '!LOGFILE!' -Tail 50 -Wait"
    goto end
)

:: Show all logs interleaved using PowerShell
echo  Tailing all logs (Ctrl+C to stop)
echo  ────────────────────────────────────────────────────
powershell -NoProfile -Command ^
    "$jobs = @('poller','web','scheduler') | ForEach-Object { $name=$_; Start-Job -ScriptBlock { param($f,$n) Get-Content $f -Tail 20 -Wait | ForEach-Object { Write-Host \"[$n] $_\" } } -ArgumentList '%LOGS_DIR%\'+$name+'.log', $name }; $jobs | Wait-Job | Receive-Job"

goto end

:end
endlocal
