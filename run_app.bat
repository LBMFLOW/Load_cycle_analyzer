@echo off
setlocal

cd /d "%~dp0"

set "PYTHONPATH=%CD%\src"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m battery_cycle_analyzer.main
if errorlevel 1 (
    echo.
    echo Battery Cycle Analyzer failed to start.
    echo Make sure dependencies are installed with:
    echo     python -m pip install -e ".[dev]"
    echo.
    pause
)

endlocal
