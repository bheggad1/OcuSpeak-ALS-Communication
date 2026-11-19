@echo off
cd /d "%~dp0"
echo Installing OcuSpeak...
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python is not installed. Install Python 3.12 from python.org
  echo and tick "Add python.exe to PATH" during setup. Then run this again.
  pause
  exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Something went wrong installing packages. See the messages above.
  pause
  exit /b 1
)
echo.
echo Done! Double-click run.bat to start OcuSpeak.
pause
