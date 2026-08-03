@echo off
setlocal

if not exist ".env" copy ".env.template" ".env" >nul

docker compose --env-file .env up -d
if errorlevel 1 exit /b 1

docker compose --env-file .env ps
echo.
echo Liguan middleware is ready. Configure ..\.env.local before starting the API.
