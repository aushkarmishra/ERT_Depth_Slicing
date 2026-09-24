@echo off
REM ============================================================
REM  ERT Resistivity Heatmap Generator - Windows Launcher
REM  Creates a virtual environment, installs dependencies,
REM  and launches the Streamlit app in your default browser.
REM ============================================================

setlocal

set VENV_DIR=venv

echo ==============================================
echo  ERT Heatmap App - Setup and Launch
echo ==============================================

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH. Please install Python 3.9+ from python.org
    pause
    exit /b 1
)

REM Create virtual environment if it does not exist
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip >nul

echo Installing required packages (this may take a few minutes on first run)...
pip install streamlit pandas scipy matplotlib pyproj numpy

echo.
echo ==============================================
echo  Launching ERT Heatmap Web Application...
echo ==============================================
echo The app will open automatically in your browser.
echo Close this window to stop the server.
echo.

streamlit run 2.location_resistivity_combiner.py

pause
endlocal
