@echo off
:: ============================================================================
:: ConFireTV — Windows Service Uninstaller
:: Run as Administrator
:: ============================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Run as Administrator required.
    pause & exit /b 1
)

echo.
echo  Stopping and removing ConFireTV services...
for %%S in (ConFireTV-Scheduler ConFireTV-Web ConFireTV-Poller) do (
    nssm stop   %%S >nul 2>&1
    nssm remove %%S confirm >nul 2>&1
    echo  [REMOVED] %%S
)
echo.
echo  All services removed. Logs and data are kept in the project folder.
echo  To also delete logs: del /q logs\*.log
echo.
pause
