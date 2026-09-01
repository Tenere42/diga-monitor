@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0.."

if not exist ".env.local" (
    echo Bitte kopiere .env.local.example zu .env.local und trage dort deinen echten BREVO_API_KEY und die echte Aufbewahrungsdauer ein, dann starte dieses Skript erneut.
    pause
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env.local") do (
    if not "%%A"=="" set "%%A=%%B"
)

set "NEWSLETTER_LEGAL_READY=true"
set "BREVO_DOI_REDIRECT_URL=http://localhost:8501/?view=confirmed"

echo Der lokale DiGA-Tracker startet. Im Browser: http://localhost:8501

where python >nul 2>nul
if not errorlevel 1 goto run_python

where py >nul 2>nul
if not errorlevel 1 goto run_py

echo Python wurde nicht gefunden. Bitte installiere Python und starte dieses Skript erneut.
pause
exit /b 1

:run_python
python -m streamlit run app.py
exit /b %errorlevel%

:run_py
py -m streamlit run app.py
exit /b %errorlevel%
