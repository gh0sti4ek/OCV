FROM python:3.10-slim

# Устанавливаем системные библиотеки для работы с изображениями
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала устанавливаем Torch для CPU (он весит меньше и не требует видеокарты)
RUN pip install --no-cache-dir torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cpu

# Копируем зависимости и ставим остальное
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем папку для временных файлов
RUN mkdir -p static/uploads