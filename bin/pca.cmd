@echo off
REM Windows launcher for PC Upgrade Advisor.
REM Prefers the installed entry point; falls back to `python -m pca`.

where pca-cli >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  pca-cli %*
  exit /b %ERRORLEVEL%
)

python -m pca %*
exit /b %ERRORLEVEL%
