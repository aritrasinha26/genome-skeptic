@echo off
setlocal
cd /d "%~dp0"

where cursor >nul 2>nul
if %errorlevel%==0 (
  start "" cursor "%~dp0GenomeSkeptic.code-workspace"
  exit /b 0
)

if exist "%LOCALAPPDATA%\Programs\cursor\Cursor.exe" (
  start "" "%LOCALAPPDATA%\Programs\cursor\Cursor.exe" "%~dp0GenomeSkeptic.code-workspace"
  exit /b 0
)

if exist "%LOCALAPPDATA%\Programs\Cursor\Cursor.exe" (
  start "" "%LOCALAPPDATA%\Programs\Cursor\Cursor.exe" "%~dp0GenomeSkeptic.code-workspace"
  exit /b 0
)

if exist "%ProgramFiles%\Cursor\Cursor.exe" (
  start "" "%ProgramFiles%\Cursor\Cursor.exe" "%~dp0GenomeSkeptic.code-workspace"
  exit /b 0
)

echo Cursor was not found automatically.
echo Open Cursor, choose File ^> Open Workspace from File, and select GenomeSkeptic.code-workspace.
pause
