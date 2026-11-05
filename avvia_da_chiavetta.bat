@echo off
cd /d "%~dp0"
echo ===================================================
echo   Starting Bottega Leonardesca via Docker...
echo ===================================================

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env file from default template.
)

docker compose up -d --build
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Please make sure Docker Desktop is running on this PC.
    pause
    exit /b 1
)

echo.
echo System active! Opening browser at http://localhost:8501 ...
timeout /t 3 >nul
start http://localhost:8501
pause