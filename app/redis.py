import json
import redis
from typing import Optional, Any
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .utils import logger
from .settings import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

# Redis 連接池
_redis_pool = None
_redis_process = None
# 模擬 Redis 實例
_fake_redis = None
# 是否使用模擬 Redis
_use_fake_redis = False

router = APIRouter(tags=["redis"])


@router.get("/kol-info")
async def get_kol_info_endpoint():
    try:
        kol_info = get_redis_key("sheet:kol_info", default=[])
        return JSONResponse({"kol_info": kol_info})
    except Exception as e:
        logger.error(f"獲取 KOL info 時出錯: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/kol-data")
async def get_kol_data_endpoint():
    try:
        kol_data = get_redis_key("sheet:kol_data", default=[])
        return JSONResponse({"kol_data": kol_data})
    except Exception as e:
        logger.error(f"獲取 KOL data 時出錯: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

def is_redis_running(host: str = REDIS_HOST, port: int = REDIS_PORT) -> bool:
    """檢查 Redis 是否在運行中"""
    try:
        r = redis.Redis(
            host=host,
            port=port,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            socket_timeout=1
        )
        return r.ping()
    except (redis.ConnectionError, redis.TimeoutError, ConnectionRefusedError):
        return False


def get_redis_connection() -> redis.Redis:
    """獲取 Redis 連接

    Returns:
        Redis 連接物件
    """
    global _redis_pool, _fake_redis, _use_fake_redis

    # 如果使用模擬 Redis
    if _use_fake_redis:
        try:
            import fakeredis
            logger.debug("使用 fakeredis 連接")
            return fakeredis.FakeRedis(server=_fake_redis, decode_responses=True)
        except ImportError:
            logger.error("fakeredis 模組不可用")
            raise RuntimeError("Redis 連接失敗")

    # 如果連接池不存在或已關閉，創建新的連接池
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True  # 自動將 bytes 轉為 str
        )

    return redis.Redis(connection_pool=_redis_pool)


def set_redis_key(key: str, value: Any, expire: Optional[int] = None) -> bool:
    """設置 Redis 鍵值

    Args:
        key: 鍵名
        value: 值 (將自動轉換為 JSON 字符串)
        expire: 過期時間 (秒)，None 表示永不過期

    Returns:
        是否成功設置
    """
    try:
        r = get_redis_connection()
        # 將複雜數據結構轉為 JSON
        if not isinstance(value, (str, int, float, bool)):
            value = json.dumps(value)
        r.set(key, value)
        if expire is not None:
            r.expire(key, expire)
        return True
    except Exception as e:
        logger.error(f"設置 Redis 鍵 {key} 時出錯: {str(e)}")
        return False


def get_redis_key(key: str, default: Any = None) -> Any:
    """獲取 Redis 鍵值

    Args:
        key: 鍵名
        default: 如果鍵不存在，返回的默認值

    Returns:
        鍵值，如果值為 JSON 字符串會自動解析為 Python 對象
    """
    try:
        r = get_redis_connection()
        value = r.get(key)
        if value is None:
            return default

        # 嘗試解析 JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    except Exception as e:
        logger.error(f"獲取 Redis 鍵 {key} 時出錯: {str(e)}")
        return default


def delete_redis_key(key: str) -> bool:
    """刪除 Redis 鍵

    Args:
        key: 鍵名

    Returns:
        是否成功刪除
    """
    try:
        r = get_redis_connection()
        r.delete(key)
        return True
    except Exception as e:
        logger.error(f"刪除 Redis 鍵 {key} 時出錯: {str(e)}")
        return False


async def stop_redis_server():
    """停止 Redis 服務器"""
    global _redis_process, _use_fake_redis, _fake_redis
    if _redis_process is not None:
        logger.info("正在停止 Redis 服務器...")
        _redis_process.terminate()
        _redis_process.wait()
        _redis_process = None
        logger.info("Redis 服務器已停止")

    # 清理模擬 Redis
    if _use_fake_redis and _fake_redis is not None:
        logger.info("清理模擬 Redis 資源")
        _fake_redis = None
        _use_fake_redis = False


def close_redis_pool():
    """關閉 Redis 連接池"""
    global _redis_pool
    if _redis_pool is not None:
        logger.info("正在關閉 Redis 連接池...")
        _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis 連接池已關閉")


def cleanup_redis():
    """清理 Redis 資源"""
    close_redis_pool()
    stop_redis_server()


def scan_redis_keys(pattern: str) -> list:
    """用 pattern 掃描所有符合的 redis key

    Args:
        pattern: redis key pattern (如 'messages:sessionid-*')
    Returns:
        符合的 key list
    """
    try:
        r = get_redis_connection()
        return list(r.scan_iter(pattern))
    except Exception as e:
        logger.error(f"scan redis keys 失敗: {str(e)}")
        return []
