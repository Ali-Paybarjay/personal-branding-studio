@echo off
rem Gets the latest version of the studio. Your data (the data and brand folders) is not touched.
chcp 65001 >nul
cd /d "%~dp0"
echo Getting the latest version...
git pull --ff-only
if %errorlevel%==0 (
  echo Done. Close the studio window and open it again.
) else (
  echo Update failed. See the message above.
)
winget upgrade --id yt-dlp.yt-dlp -e --silent >nul 2>nul
pause
