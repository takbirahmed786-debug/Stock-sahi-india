@echo off
cd /d "%~dp0"
echo StockSahi India - Starting...
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
  echo Please install Python 3.11 or 3.12 from python.org first.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:5000"
py -3 app.py
pause
