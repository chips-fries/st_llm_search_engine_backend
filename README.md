# ST LLM Search Engine Backend

FastAPI + Redis + Google Sheet API server for LLM search engine.

- 適合部署到 Render、Railway、Fly.io 等雲平台
- 使用 poetry 管理 Python 依賴
- 支援 Google Sheet、Gemini API、Redis（本地或 fakeredis）

## 開發

```bash
poetry install
poetry run uvicorn app.app:app --reload --host 0.0.0.0 --port 10000
```

## Docker 部署

```bash
docker build -t st-llm-backend .
docker run -p 10000:10000 st-llm-backend
```

## Render 部署
- Web Service
- Start Command: `poetry run uvicorn app.app:app --host 0.0.0.0 --port 10000`
- Port: 10000
- 設定環境變數（Google/Sheet/Gemini/Redis） 