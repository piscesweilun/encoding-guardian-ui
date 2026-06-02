@echo off
setlocal
cd /d "%~dp0"
netstat -ano | findstr ":8000" >nul
if not errorlevel 1 (
  echo Port 8000 is already in use. Open http://127.0.0.1:8000/ or stop the existing server first.
  start "" "http://127.0.0.1:8000/"
  pause
  exit /b 0
)
start "" "http://127.0.0.1:8000/"
python server.py --host 127.0.0.1 --port 8000
if errorlevel 1 (
  echo.
  echo Encoding Guardian failed to start. Make sure Python is installed and available in PATH.
  pause
)
