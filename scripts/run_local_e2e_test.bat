@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0.."

if not exist ".env.local" (
    echo FEHLER: .env.local wurde nicht gefunden.
    pause
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env.local") do (
    if not "%%A"=="" set "%%A=%%B"
)

set "NEWSLETTER_LEGAL_READY=true"
set "BREVO_DOI_REDIRECT_URL=http://localhost:8501/?view=confirmed"

where python >nul 2>nul
if errorlevel 1 (
    echo FEHLER: Python wurde nicht gefunden.
    pause
    exit /b 1
)

echo.
echo Pruefe Python-Abhaengigkeiten...
python -m streamlit --version >nul 2>nul

if errorlevel 1 (
    echo Streamlit ist noch nicht installiert.
    echo Installiere jetzt die Projekt-Abhaengigkeiten...
    python -m pip install -r requirements.txt

    if errorlevel 1 (
        echo.
        echo FEHLER bei der Installation der Abhaengigkeiten.
        pause
        exit /b 1
    )
)

echo.
echo Starte lokalen DiGA Tracker...
echo Browser: http://localhost:8501
echo.

python -m streamlit run app.py

echo.
echo Der DiGA Tracker wurde beendet oder es ist ein Fehler aufgetreten.
pause
