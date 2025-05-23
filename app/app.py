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
    # 預熱 Google Sheet 數據到 Redis，增加重試機制
    retries = 0
    max_retries = 3
    success = False
    
    while retries < max_retries and not success:
        try:
            logger.info(f"預熱 Google Sheet 三張表到 Redis cache (嘗試 {retries+1}/{max_retries}) ...")
            
            # 加載 KOL info
            kol_info = sheet_manager.get_kol_info(force_refresh=True)
            logger.info(f"KOL info 預熱完成: {len(kol_info)} 筆")
            
            # 加載 saved searches
            saved_searches = sheet_manager.get_saved_searches(force_refresh=True)
            logger.info(f"Saved searches 預熱完成: {len(saved_searches)} 筆")
            
            # 加載 KOL data
            kol_data = sheet_manager.get_kol_data(force_refresh=True)
            logger.info(f"KOL data 預熱完成: {len(kol_data)} 筆")
            
            logger.info("Google Sheet 預熱全部完成")
            success = True
        except Exception as e:
            retries += 1
            logger.error(f"Google Sheet 預熱嘗試 {retries}/{max_retries} 失敗: {e}")
            if retries < max_retries:
                logger.info(f"等待 5 秒後重試...")
                import time
                time.sleep(5)
    
    if not success:
        logger.error("Google Sheet 預熱失敗次數已達上限，服務可能無法正常工作")

