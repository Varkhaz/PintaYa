@echo off
REM Genera PintaYa.exe portable (un solo archivo, no requiere instalacion ni administrador).
REM Requisito: Python 3.10+ para Windows (python.org) en la maquina donde se compila.
REM El exe resultante NO necesita Python en el equipo del niño.
python -m pip install --user -r requirements.txt || goto :err
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PintaYa ^
  --collect-all pillow_heif --collect-submodules pymupdf app.py || goto :err
echo.
echo Listo: dist\PintaYa.exe
pause
exit /b 0
:err
echo Hubo un error en la compilacion.
pause
exit /b 1
