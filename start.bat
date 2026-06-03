@echo off
rem ============================================================================
rem Windows launcher for Blinkit MCP. Mirror of start.sh (used on macOS/Linux).
rem
rem CRITICAL: this process's stdout is the MCP JSON-RPC protocol channel. ALL
rem non-protocol output MUST go to stderr (1>&2). Only the final "uv run main.py"
rem writes to stdout, where it carries the JSON-RPC messages. cmd passes a child's
rem stdout through unmodified, so the server speaks to the host directly.
rem ============================================================================
setlocal EnableExtensions

rem Self-reinvoke entry point for the background Playwright Firefox install.
if /I "%~1"=="--install-firefox" goto :install_firefox

rem Move to this script's directory.
cd /d "%~dp0"

rem Add common uv install locations to PATH (matches start.sh).
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"

rem Ensure uv is available; install it via the official Windows installer if missing.
where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found. Installing... 1>&2
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" 1>&2
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
) else (
    for /f "delims=" %%i in ('where uv') do echo uv found at: %%i 1>&2
)

rem Ensure dependencies are installed (must complete before the server starts).
echo Syncing dependencies... 1>&2
uv sync --frozen 1>&2

rem Marker files coordinate the background Firefox install with server.py, which
rem waits on ".playwright_installing" before launching the browser. Set the marker
rem in the FOREGROUND (before spawning the background job) so an early tool call
rem cannot slip past it while the background cmd is still starting up.
set "BLINKIT_DIR=%USERPROFILE%\.blinkit_mcp"
if not exist "%BLINKIT_DIR%" mkdir "%BLINKIT_DIR%"
del /q "%BLINKIT_DIR%\.playwright_ready" >nul 2>nul
type nul > "%BLINKIT_DIR%\.playwright_installing"

rem Run "playwright install firefox" in the background (re-invokes this script with
rem --install-firefox) so the server starts immediately and answers the initialize
rem handshake without timing out. The background job redirects its own output to a
rem log file, so nothing reaches stdout (the MCP channel).
echo Ensuring Playwright Firefox is installed (background)... 1>&2
start "blinkit-firefox-install" /b cmd /c ""%~f0" --install-firefox"

rem Launch the server. Its stdout is the MCP protocol channel; uv's stderr stays
rem on stderr.
echo Starting Blinkit MCP... 1>&2
uv run main.py
exit /b %errorlevel%

rem ----------------------------------------------------------------------------
:install_firefox
rem Background job: install Firefox, then flip the markers. All command output is
rem routed to a log file so none of it reaches the parent's stdout (MCP channel).
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
set "BLINKIT_DIR=%USERPROFILE%\.blinkit_mcp"
uv run playwright install firefox > "%BLINKIT_DIR%\playwright_install.log" 2>&1
if not errorlevel 1 type nul > "%BLINKIT_DIR%\.playwright_ready"
del /q "%BLINKIT_DIR%\.playwright_installing" >nul 2>nul
exit /b
