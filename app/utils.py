import os
import sys
import logging
from logging.handlers import RotatingFileHandler

from .settings import LOG_DIR, LOG_MAX_SIZE, LOG_BACKUP_COUNT, LOG_LEVEL

# 確保日誌目錄存在
os.makedirs(LOG_DIR, exist_ok=True)

# 設置全局日誌配置
LOGGER_INITIALIZED = False
LOGGERS = {}

# 日誌級別映射
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def reset_logging():
    """重置所有日誌配置，停用現有 handlers

    這個函數將移除所有已設定的 logging handlers，使後續設定能重新配置日誌系統。
    """
    global LOGGER_INITIALIZED

    # 獲取根日誌記錄器
    root_logger = logging.getLogger()

    # 移除所有 handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 重置初始化標誌
    LOGGER_INITIALIZED = False

    # 清空 LOGGERS 緩存
    LOGGERS.clear()

    return True


def configure_logging(level="info"):
    """配置全局日誌系統

    Args:
        level: 日誌級別 (debug, info, warning, error, critical)
    """
    global LOGGER_INITIALIZED

    if LOGGER_INITIALIZED:
        return

    # 獲取日誌級別
    log_level = LOG_LEVELS.get(level.lower(), logging.INFO)

    # 清空先前可能存在的 handlers
    reset_logging()

    # 創建根處理器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 創建控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [PID:%(process)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S,%f"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # 創建文件處理器 - 使用單一日誌檔案
    log_file = os.path.join(LOG_DIR, "st_llm_search_engine.log")

    # 清空日誌檔案 - 每次重啟時都重新開始
    with open(log_file, "w") as f:
        f.write("")

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_SIZE,
        backupCount=LOG_BACKUP_COUNT
    )
    file_handler.setLevel(log_level)
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [PID:%(process)d] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S,%f"
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    # 定義關鍵 logger 名稱列表
    important_loggers = [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi"
    ]

    # 設定這些 logger 使其傳播日誌到根 logger
    for logger_name in important_loggers:
        logger = logging.getLogger(logger_name)
        logger.handlers = []  # 移除任何現有的處理器
        logger.propagate = True  # 確保消息傳播到根 logger

    # 標記日誌系統已初始化
    LOGGER_INITIALIZED = True

    root_logger.info(f"日誌系統已配置，級別為 {level}")
    root_logger.info(f"所有日誌將寫入 {log_file}")


def get_logger(name):
    """獲取指定名稱的日誌器

    Args:
        name: 日誌器名稱

    Returns:
        Logger 實例
    """
    global LOGGERS

    # 如果日誌系統未初始化，則進行初始化
    if not LOGGER_INITIALIZED:
        configure_logging(LOG_LEVEL)

    # 檢查是否已有此名稱的日誌器
    if name in LOGGERS:
        return LOGGERS[name]

    # 創建新日誌器
    logger = logging.getLogger(name)
    LOGGERS[name] = logger

    return logger


logger = get_logger("root")


