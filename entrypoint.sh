#!/bin/sh
set -e

# 這裡可以寫 secret json 的處理
mkdir -p /app/credentials
echo "$GOOGLE_SERVICE_ACCOUNT_JSON" | base64 -d > /app/credentials/service_account.json

# 啟動 redis-server（背景執行）
redis-server --daemonize yes

# 等待 redis ready
until redis-cli ping | grep -q PONG; do
  echo "Waiting for Redis to be ready..."
  sleep 0.5
done

# 啟動 FastAPI
exec poetry run uvicorn app.app:app --host 0.0.0.0 --port 10000 --workers 4 --no-access-log