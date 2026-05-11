@echo off
chcp 936 >nul
echo.
echo ========================================
echo    ChangTeng Cloud Server
echo ========================================
echo.

:: Check if ports are already in use
echo Checking ports...
netstat -an | findstr "5032" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [WARNING] Port 5032 is already in use!
    echo Stopping existing processes...
    taskkill /F /IM python.exe 2>nul
    timeout /t 3 /nobreak >nul
) else (
    echo Port 5032 is available
)

echo.
echo Starting servers...
echo.

:: Start Contract Server in window 1
echo [1/2] Starting Contract Server (Port 5032)...
start "Contract Server - Port 5032" cmd /k "echo Contract Server Starting... && python contract_server.py"

timeout /t 3 /nobreak >nul

:: Start Cloud Sync Server (WebSocket) in window 2
echo [2/2] Starting Cloud Sync Server WebSocket (Port 5033)...
start "Cloud Sync Server WS - Port 5033" cmd /k "echo Cloud Sync Server WebSocket Starting... && python cloud_sync_server_ws.py"

timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo    Servers started successfully!
echo ========================================
echo.
echo Contract Server:   http://localhost:5032
echo Cloud Sync (WS):   ws://localhost:5033
echo.
echo [Note] Two windows are open showing server logs
echo.
echo Press any key to stop all servers...
pause >nul

:: Stop servers
echo.
echo Stopping servers...
taskkill /F /FI "WINDOWTITLE eq Contract Server - Port 5032" 2>nul
taskkill /F /FI "WINDOWTITLE eq Cloud Sync Server WS - Port 5033" 2>nul
taskkill /F /IM python.exe 2>nul
echo.
echo Servers stopped.
timeout /t 2 /nobreak >nul
