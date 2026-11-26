@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Python environment missing. See SUBMISSION.txt for setup.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo Web build missing. Run npm.cmd run build in frontend first.
  pause
  exit /b 1
)
if /I "%~1"=="offline" set "LLM_PROVIDER=mock"
echo SafeTurn local demo: http://127.0.0.1:8000
echo Keep this window open. Press Ctrl+C to stop.
cd backend
".venv\Scripts\python.exe" -X utf8 -m uvicorn serve:app --host 127.0.0.1 --port 8000
if errorlevel 1 pause
