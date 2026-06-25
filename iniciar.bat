@echo off
cd /d "%~dp0"
title Live Translator
echo ============================================
echo    Live Translator
echo    Acesse: http://localhost:8001
echo    (o navegador abre sozinho em instantes)
echo    Para PARAR: feche esta janela ou Ctrl+C
echo ============================================
echo.

rem Libera a porta 8001 se algo antigo estiver preso nela
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "127.0.0.1:8001 .*LISTENING"') do taskkill /F /PID %%P >nul 2>&1

rem Abre o navegador depois que o servidor sobe (5s)
start "" /min powershell -NoProfile -Command "Start-Sleep 5; Start-Process 'http://localhost:8001'"

rem Inicia o servidor (usa o Python 3.14 que tem as dependencias)
py -3.14 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

pause
