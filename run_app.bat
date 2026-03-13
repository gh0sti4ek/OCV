@echo off
if exist venv\Scripts\activate call venv\Scripts\activate

echo Starting MinIO Server...
:: Запускаем сервер MinIO. Убедись, что путь C:\minio_server\data существует
start "MinIO" cmd /k "C:\minio_server\minio.exe server C:\minio_server\data --console-address :9001"

echo Starting Redis...
start "Redis Server" redis-server.exe

echo Starting Celery Worker...
:: У тебя в батнике ошибка: файл называется tasks.py, а в команде указано -A tasks
start "Celery Worker" cmd /k "python -m celery -A tasks worker --loglevel=info --pool=solo"

echo Starting Flask App...
start "Flask App" cmd /k "python app.py"

echo All services are starting up.
pause