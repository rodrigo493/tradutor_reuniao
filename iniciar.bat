@echo off
cd /d "%~dp0"
echo Iniciando Live Translator...
echo Acesse: http://localhost:8001
echo Pressione Ctrl+C para parar.
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
pause
