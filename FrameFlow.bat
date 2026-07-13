@echo off
chcp 65001 >nul
title FrameFlow
color 0B
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║           FrameFlow v1.0             ║
echo  ║   Цепочная генерация видео           ║
echo  ╚══════════════════════════════════════╝
echo.

if not exist ".env" (
  echo [!] Первый запуск — создаю файл .env из шаблона...
  copy /Y ".env.example" ".env" >nul
  echo     Откройте FrameFlow в браузере и нажмите "Настройки" — вставьте API-ключ.
  echo.
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [!] ffmpeg не найден в PATH.
  echo     Установите: https://ffmpeg.org/download.html
  echo     Без ffmpeg не работает склейка клипов и цепочка кадров.
  echo.
)

if not exist "venv" (
  echo [*] Создаю виртуальное окружение Python...
  py -3 -m venv venv 2>nul || python -m venv venv
  if errorlevel 1 (
    echo [X] Не удалось создать venv. Установите Python 3.10+ с python.org
    pause
    exit /b 1
  )
)

call venv\Scripts\activate.bat

echo [*] Проверяю зависимости...
pip install -q -r requirements.txt

cd studio

echo [*] Запускаю FrameFlow на http://127.0.0.1:8765
echo     Закройте это окно для остановки сервера.
echo.

start "" "http://127.0.0.1:8765"
python -m uvicorn app:app --host 127.0.0.1 --port 8765

if errorlevel 1 (
  echo.
  echo [X] Сервер завершился с ошибкой. Порт 8765 занят?
  pause
)
