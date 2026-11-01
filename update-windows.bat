@echo off
rem Gets the latest version of the studio. Your data (the data and brand folders) is not touched.
chcp 65001 >nul
cd /d "%~dp0"
echo Getting the latest version...
git pull --ff-only
if %errorlevel%==0 (
  echo Done. Close the studio window and open it again.
) else (
  echo.
  echo Could not update automatically, probably because you changed the studio's code yourself.
  echo Your data is safe. To merge the new version with your changes, open PowerShell and run:
  echo     cd "%~dp0"
  echo     claude
  echo and ask Claude to get the latest version of the studio from GitHub and merge it with your changes.
)
winget upgrade --id yt-dlp.yt-dlp -e --silent >nul 2>nul
pause
