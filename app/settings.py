import os
from typing import Dict, Any
from pydantic import BaseModel, Field

# Redis 相關設定
REDIS_HOST = os.environ.get("ST_LLM_REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("ST_LLM_REDIS_PORT", "6379"))
REDIS_DB = 0
REDIS_PASSWORD = os.environ.get("ST_LLM_REDIS_PASSWORD", None)

# Gemini 模型設定
GEMINI_MODEL = os.environ.get("ST_LLM_GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 日誌設定
LOG_DIR = "/tmp/st_llm_search_engine"
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 10
LOG_LEVEL = os.environ.get("ST_LLM_LOG_LEVEL", "info").lower()

# Session 相關設定
SESSION_EXPIRE = 60 * 60 * 24       # Session 過期時間 (1天)

