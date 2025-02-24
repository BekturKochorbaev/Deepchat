FROM python:3.12-slim

# Установка зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN curl --connect-timeout 600 -sSL https://install.python-poetry.org | python3 -

# Добавляем Poetry в PATH
ENV PATH="/root/.local/bin:$PATH"

# Увеличиваем таймаут для Poetry
ENV POETRY_HTTP_TIMEOUT=600

# Используем другой индекс пакетов
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock* ./

# Устанавливаем зависимости
RUN poetry install --no-interaction --no-ansi

# Копируем код
COPY . .

# Открываем порт
EXPOSE 8000

# Запуск приложения
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
