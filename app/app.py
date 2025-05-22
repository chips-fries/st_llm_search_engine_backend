from . import utils
from .utils import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from .sheet import router as sheet_router, sheet_manager
from .session import router as session_router
from .redis import router as redis_router


# 確保日誌系統已初始化，使用配置的格式
utils.configure_logging()

# 創建 FastAPI 應用實例
app = FastAPI()

# 允許跨域請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加 API 路由
# app.include_router(gemini_router, prefix="/api", tags=["gemini"])
app.include_router(session_router, prefix="/api", tags=["session"])
app.include_router(sheet_router, prefix="/api", tags=["sheet"])
app.include_router(redis_router, prefix="/api/redis", tags=["redis"])

# 根路徑重定向到前端頁面
@app.get("/")
async def index():
    return RedirectResponse(url="/ui/")

# 健康檢查端點
@app.get("/ping")
async def ping():
    return {"status": "ok"}


# 應用程序生命週期管理
@app.on_event("startup")
async def startup_event():
    logger.info("==================================================")
    logger.info("API 服務器啟動")
    logger.info("==================================================")
    # 只做預熱
    try:
        logger.info("預熱 Google Sheet 三張表到 Redis cache ...")
        sheet_manager.get_kol_info(force_refresh=True)
        sheet_manager.get_saved_searches(force_refresh=True)
        sheet_manager.get_kol_data(force_refresh=True)
        logger.info("Google Sheet 預熱完成")
    except Exception as e:
        logger.error(f"Google Sheet 預熱失敗: {e}")

