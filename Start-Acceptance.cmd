@echo off
setlocal
if "%~2"=="" goto usage
set "PYTHONIOENCODING=utf-8"
set "UV_PROJECT_ENVIRONMENT=%~1\.venv"
uv --directory "%~dp0." --cache-dir "%~1\.uv-cache" --offline run --no-sync python -m tools.acceptance_demo --knowledge-repo "%~1" --data-dir "%~2" --formal-db "%~3"
set "SSR_ACCEPTANCE_EXIT=%ERRORLEVEL%"
if not "%SSR_ACCEPTANCE_EXIT%"=="0" pause
exit /b %SSR_ACCEPTANCE_EXIT%
:usage
echo Usage: Start-Acceptance.cmd "knowledge checkout" "private acceptance output" ["formal knowledge.sqlite3"]
echo Uses the existing knowledge .venv only. No install or environment creation.
pause
exit /b 2
