@echo off
rem Turing launcher. First run installs everything, then opens the Turing app.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo First run: installing Turing. This takes a few minutes...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo Python 3.11 or newer is required: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (pause & exit /b 1)
    ".venv\Scripts\python.exe" scripts\create_shortcuts.py
)
start "" ".venv\Scripts\pythonw.exe" -m turing.desktop