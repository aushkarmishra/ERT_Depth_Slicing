@echo off
REM ERT Data Processor - Windows quick-start script
REM Double-click this file to set up (first run only) and launch the app.

cd /d "%~dp0"

IF NOT EXIST venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing/checking dependencies...
pip install -r requirements.txt --quiet

echo Launching ERT Data Processor in your default browser...
streamlit run 3.ert_dep_slr_app.py

pause
