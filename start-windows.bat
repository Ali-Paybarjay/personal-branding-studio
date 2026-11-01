@echo off
rem Opens Content Studio. Keep this window open while you use the studio; close it to stop.
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1
curl -s -o nul -m 1 http://127.0.0.1:7788/api/state && (start "" http://127.0.0.1:7788 & exit /b)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app\server.py
) else (
  python app\server.py
)
echo.
echo The studio stopped. If you see an error above, send a screenshot of this window.
pause
