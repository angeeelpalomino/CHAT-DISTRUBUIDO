@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Instalando Flask...
    python -m pip install -r requirements.txt
)

echo.
echo Abre en esta computadora: http://127.0.0.1:5000
echo Comparte con el salon:    http://192.168.102.5:5000
echo.
python app.py

pause
