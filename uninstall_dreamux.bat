@echo off
chcp 65001 >nul
net session >nul 2>&1
if errorlevel 1 (
    echo Требуются права администратора.
    pause
    exit /b 1
)

echo ============================================================
echo   Полное удаление DreamUX
echo ============================================================
echo.
echo Будут удалены:
echo   - Все VHD-файлы в T:\DreamUX\vfs\
echo   - users.json, disks.json
echo   - Задача в Планировщике (DreamUXBoot)
echo.
set /p confirm="Продолжить? (y/N): "
if /i not "%confirm%"=="y" exit /b 0

echo.
echo [1] Удаляю задачу из Планировщика...
schtasks /End /TN "DreamUXBoot" >nul 2>&1
schtasks /Delete /TN "DreamUXBoot" /F >nul 2>&1

echo [2] Удаляю VHD-файлы...
if exist "T:\DreamUX\vfs\disk0.vhd" del /f /q "T:\DreamUX\vfs\disk0.vhd"
if exist "T:\DreamUX\vfs\disk1.vhd" del /f /q "T:\DreamUX\vfs\disk1.vhd"
if exist "T:\DreamUX\vfs\disk2.vhd" del /f /q "T:\DreamUX\vfs\disk2.vhd"
if exist "T:\DreamUX\vfs\disks.json" del /f /q "T:\DreamUX\vfs\disks.json"

echo [3] Удаляю users.json и логи...
if exist "T:\DreamUX\users.json" del /f /q "T:\DreamUX\users.json"
if exist "T:\DreamUX\plugins\gnome_gui\logs\*.log" del /f /q "T:\DreamUX\plugins\gnome_gui\logs\*.log"

echo.
echo [OK] DreamUX удалена.
echo Исходный код (kernel.py, plugins\) остался.
echo.
pause
