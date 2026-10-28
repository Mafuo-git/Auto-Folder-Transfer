@echo off
setlocal
cd /d "%~dp0"

echo Installing build dependencies on this PC...
py -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed

echo Building TransfertMotec.exe...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name TransfertMotec transfer_app.py
if errorlevel 1 goto :failed

if not exist "dist\TransfertMotec.exe" goto :failed

echo.
echo Standalone executable created: "%~dp0dist\TransfertMotec.exe"
echo Copy this file to the simulator PC.
exit /b 0

:failed
echo.
echo Build failed. Check the error above.
exit /b 1
