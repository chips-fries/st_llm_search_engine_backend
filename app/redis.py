import json
import subprocess
import time
import redis
from typing import Optional, Any, Tuple, List, Dict
from datetime import datetime
from fastapi import APIRouter, Query
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

# @router.get("/saved-searches")
# async def get_saved_searches_endpoint(session_id: str):
#     try:
#         searches = get_saved_searches(session_id)
#         return JSONResponse({"searches": searches})
#     except Exception as e:
#         logger.error(f"獲取已保存搜索時出錯: {str(e)}")
#         return JSONResponse({"error": str(e)}, status_code=500)

# @router.post("/saved-searches")
# async def create_saved_search_endpoint(session_id: str, search: Dict[str, Any]):
#     try:
#         saved_search = save_search(session_id, search)
#         return JSONResponse(saved_search)
#     except Exception as e:
#         logger.error(f"保存搜索時出錯: {str(e)}")
#         return JSONResponse({"error": str(e)}, status_code=500)

# @router.delete("/saved-searches")
# async def delete_saved_searches_endpoint(
#     session_id: str,
#     search_ids: List[int] = Query(...)
# ):
#     try:
#         success = delete_searches(session_id, search_ids)
#         return JSONResponse({"success": success})
#     except Exception as e:
#         logger.error(f"刪除搜索時出錯: {str(e)}")
#         return JSONResponse({"error": str(e)}, status_code=500)

# @router.patch("/saved-searches")
# async def update_saved_search_endpoint(
#     session_id: str,
#     search_id: int,
#     update: dict
# ):
#     """
#     更新指定 session 的單筆 saved_searches
#     Args:
#         session_id: 會話 ID
#         search_id: 要更新的 search id (int)
#         update: 要更新的內容 (dict)
#     Returns:
#         更新後的 search dict
#     """
#     try:
#         searches = get_saved_searches(session_id)
#         found = False
#         for idx, s in enumerate(searches):
#             if s.get("id") == search_id:
#                 searches[idx] = {**s, **update}
#                 found = True
#                 break
#         if not found:
#             return JSONResponse(
#                 {"error": f"search_id {search_id} 不存在"}, status_code=404
#             )
#         key = f"saved_searches:{session_id}"
#         set_redis_key(key, searches)
#         return JSONResponse(searches[idx])
#     except Exception as e:
#         logger.error(f"更新 saved_searches 時出錯: {str(e)}")
#         return JSONResponse({"error": str(e)}, status_code=500)

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


# def get_saved_searches(session_id: str) -> List[Dict[str, Any]]:
#     """獲取指定會話的已保存搜索列表

#     Args:
#         session_id: 會話 ID

#     Returns:
#         已保存的搜索列表
#     """
#     key = f"saved_searches:{session_id}"
#     searches = get_redis_key(key, default=[])
#     logger.info(f"[get_saved_searches] 讀取 Redis key={key}，內容={searches}")
#     # 確保返回的數據格式正確
#     formatted_searches = []
#     for search in searches:
#         if isinstance(search, dict):
#             formatted_search = {
#                 "id": search.get("id", 0),
#                 "title": search.get("title", ""),
#                 "account": search.get("account", ""),
#                 "order": search.get("order", 0),
#                 "query": search.get("query", {}),
#                 "created_at": search.get("created_at", "")
#             }
#             formatted_searches.append(formatted_search)

#     return formatted_searches


# def save_search(session_id: str, search_data: Dict[str, Any]) -> Dict[str, Any]:
#     """保存新的搜索

#     Args:
#         session_id: 會話 ID
#         search_data: 搜索數據

#     Returns:
#         保存的搜索數據
#     """
#     searches = get_saved_searches(session_id)
#     # id: 全部 search 的最大 id + 1
#     search_id = max([s.get("id", 0) for s in searches], default=0) + 1
#     # account: 前端送來的
#     account = search_data.get("account", "")
#     # order: 該 account 下最大 order + 1
#     account_searches = [s for s in searches if s.get("account") == account]
#     order = max([s.get("order", 0) for s in account_searches], default=0) + 1

#     # 構建標準格式的搜索記錄
#     search = {
#         "id": search_id,
#         "title": search_data.get("title", f"搜索 {search_id}"),
#         "account": account,
#         "order": order,
#         "query": search_data.get("query", {}),  # 直接使用前端傳來的 query 結構
#         "created_at": datetime.now().isoformat()
#     }

#     searches.append(search)
#     key = f"saved_searches:{session_id}"
#     logger.info(f"[save_search] 寫入 Redis key={key}，內容={searches}")
#     set_redis_key(key, searches)
#     return search


# def delete_searches(session_id: str, search_ids: List[int]) -> bool:
#     """批量刪除指定的搜索

#     Args:
#         session_id: 會話 ID
#         search_ids: 要刪除的搜索 ID 列表

#     Returns:
#         是否成功刪除
#     """
#     searches = get_saved_searches(session_id)
#     searches = [s for s in searches if s["id"] not in search_ids]
#     key = f"saved_searches:{session_id}"
#     return set_redis_key(key, searches)


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
