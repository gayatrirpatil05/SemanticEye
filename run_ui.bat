@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto end
)
where py >nul 2>nul
if %errorlevel%==0 (
  py app.py
  goto end
)
echo Python 3.9 or newer is needed. Install it once from python.org, then run this again.
:end
pause
