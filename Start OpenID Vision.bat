@echo off
rem  Double-click this file to start OpenID Vision and open it in your web browser.
rem  Optional: "Start OpenID Vision.bat" 8020  (use another port if 8000 is taken)
rem  Set NO_BROWSER=1 to start without opening the browser.
title OpenID Vision - KEEP THIS WINDOW OPEN
cd /d "%~dp0"
set PORT=%~1
if "%PORT%"=="" set PORT=8000

rem  Already running? Then just open the page.
powershell -NoProfile -Command "try { Invoke-RestMethod http://127.0.0.1:%PORT%/api/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
    echo.
    echo  OpenID Vision is already running at http://127.0.0.1:%PORT%
    if not defined NO_BROWSER start "" "http://127.0.0.1:%PORT%"
    timeout /t 4 >nul
    exit /b 0
)

echo.
echo  ============================================================
echo   OpenID Vision is starting.
echo   KEEP THIS WINDOW OPEN while you use the website.
echo   When it says "Application startup complete" the website is
echo   ready at:   http://127.0.0.1:%PORT%
echo   Your browser will open by itself in a few seconds.
echo   To STOP the website: close this window.
echo  ============================================================
echo.

rem  Open the browser as soon as the server answers (waits up to about 3 minutes).
if not defined NO_BROWSER start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-RestMethod http://127.0.0.1:%PORT%/api/health -TimeoutSec 2 | Out-Null; Start-Process 'http://127.0.0.1:%PORT%'; break } catch { Start-Sleep -Seconds 2 } }"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Port %PORT%

echo.
echo  OpenID Vision has stopped. Press any key to close this window.
pause >nul
