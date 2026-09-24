@echo off
TITLE ERT Depth-Slice Heatmap & Vector Generator
echo ===================================================
echo   Setting up Virtual Environment and Dependencies
echo ===================================================

:: Check if venv directory exists, create if missing
if not exist "venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

:: Upgrade pip and install required dependencies
echo [INFO] Installing / Updating required GIS packages...
python -m pip install --upgrade pip

:: Install spatial and application dependencies
pip install numpy pandas matplotlib scipy pyproj rasterio simplekml pillow geopandas shapely fiona streamlit

echo ===================================================
echo   Launching Application...
echo ===================================================

streamlit run 4.slice2vector.py

pause