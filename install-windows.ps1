# Content Studio installer for Windows 10/11.
#   irm https://raw.githubusercontent.com/siavash-smf/personal-branding-studio/main/install-windows.ps1 | iex
# Installs Git, Python, ffmpeg and yt-dlp (winget), then Claude Code, downloads the studio to
# %USERPROFILE%\content-studio and puts a "Content Studio" shortcut on the Desktop.
# Safe to run again: anything already installed is skipped.
$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/siavash-smf/personal-branding-studio.git'
$Dir  = if ($env:STUDIO_DIR) { $env:STUDIO_DIR } else { Join-Path $HOME 'content-studio' }

function Say($m) { Write-Host "`n> $m" -ForegroundColor Cyan }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
              [Environment]::GetEnvironmentVariable('Path', 'User') + ";$HOME\.local\bin"
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  throw 'winget was not found. Install "App Installer" from the Microsoft Store, then run this again.'
}

foreach ($p in @('Git.Git', 'Python.Python.3.12', 'Gyan.FFmpeg', 'yt-dlp.yt-dlp')) {
  Say "Installing $p (skipped if already installed)"
  winget install --id $p -e --source winget --silent --accept-package-agreements --accept-source-agreements | Out-Host
}
winget upgrade --id yt-dlp.yt-dlp -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
Refresh-Path

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Say 'Installing Claude Code'
  Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
  Refresh-Path
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not on PATH yet. Close this window, open a new PowerShell and run the installer again.' }
if (Test-Path (Join-Path $Dir '.git')) {
  Say "Updating the studio in $Dir"
  git -C $Dir pull --ff-only
} else {
  Say "Downloading the studio to $Dir"
  git clone --depth 1 $Repo $Dir
}

Say 'Creating the "Content Studio" shortcut on the Desktop'
$desk = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut((Join-Path $desk 'Content Studio.lnk'))
$s.TargetPath = Join-Path $Dir 'start-windows.bat'
$s.WorkingDirectory = $Dir
$s.Save()

Write-Host @"

Done.

Next steps:
  1. Close this window and open a NEW PowerShell window.
  2. Type:  claude   and sign in with your Claude account (Pro or Max). Then type /exit
  3. Double-click "Content Studio" on your Desktop. The "Start" page opens in your browser.

"@ -ForegroundColor Green
