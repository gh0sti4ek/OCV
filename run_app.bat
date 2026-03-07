@echo off
:: ≈сли есть venv, активируем его
if exist venv\Scripts\activate call venv\Scripts\activate

echo Starting Redis...
:: ѕроверь, что redis-server.exe доступен глобально, иначе укажи полный путь
start "Redis Server" redis-server.exe

echo Starting Celery Worker...
start "Celery Worker" cmd /k "python -m celery -A tasks worker --loglevel=info --pool=solo"
echo Starting Flask App...
:: ”кажи хост, чтобы было удобнее заходить
start "Flask App" cmd /k "python app.py"

echo All services are starting up.
pause