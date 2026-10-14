@echo off
chcp 65001 >nul
net session >nul 2>&1
if errorlevel 1 (
    echo Требуются права администратора.
    pause
    exit /b 1
)

set "BOOT_SCRIPT=T:\DreamUX\boot.py"
set "PYTHON_EXE="

for /f "delims=" %%i in ('where pythonw 2^>nul') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
)
if not defined PYTHON_EXE (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
    )
)
if not defined PYTHON_EXE (
    echo Python не найден в PATH
    pause
    exit /b 1
)

echo ============================================================
echo   Установка DreamUX в автозапуск
echo ============================================================
echo.
echo Python: %PYTHON_EXE%
echo Boot:   %BOOT_SCRIPT%
echo.

schtasks /Query /TN "DreamUXBoot" >nul 2>&1
if %errorlevel%==0 schtasks /Delete /TN "DreamUXBoot" /F >nul

schtasks /Create ^
    /TN "DreamUXBoot" ^
    /TR "\"%PYTHON_EXE%\" \"%BOOT_SCRIPT%\"" ^
    /SC ONLOGON ^
    /RL HIGHEST ^
    /DELAY 0000:10 ^
    /F

if errorlevel 1 (
    echo.
    echo Не удалось создать задачу
    pause
    exit /b 1
)

echo.
echo [OK] Задача "DreamUXBoot" создана
echo      Запускается при входе пользователя через 10 секунд
echo.
echo Хочешь запустить сейчас? (Y/N)
set /p ans=
if /i "%ans%"=="Y" schtasks /Run /TN "DreamUXBoot"

echo.
echo Готово. Перезайди в Windows, чтобы проверить автозапуск.
echo.
pause
