FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y redis-server && rm -rf /var/lib/apt/lists/*

# 安裝 poetry
RUN pip install --no-cache-dir poetry

# 複製 poetry 檔案並安裝依賴
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --no-interaction --no-ansi

# 複製 app 程式碼
COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]