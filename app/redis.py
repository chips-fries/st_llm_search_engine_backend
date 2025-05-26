import json
import redis
from typing import Optional, Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import pandas as pd
from datetime import datetime, timedelta, timezone

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

@router.post("/kol-data")
async def get_filtered_kol_data(request: Request):
    try:
        data = await request.json()
        query = data.get("query", "")
        tags = data.get("tags", [])
        time_type = data.get("time", "")
        n_days = int(data.get("n", 1) or 1)

        kol_data = get_redis_key("sheet:kol_data", default=[])
        kol_info = get_redis_key("sheet:kol_info", default=[])
        if not kol_data or not kol_info:
            return JSONResponse({"kol_data": []})

        df_data = pd.DataFrame(kol_data)
        df_info = pd.DataFrame(kol_info)

        # merge kol_id
        if not df_data.empty and not df_info.empty:
            df = pd.merge(df_data, df_info, on="kol_id", how="left", suffixes=("", "_info"))
        else:
            df = df_data

        # 時間篩選
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        if time_type == 0:
            # 昨日 00:00:00 ~ 23:59:59 (台北)
            y = now - timedelta(days=1)
            y_start = y.replace(hour=0, minute=0, second=0, microsecond=0)
            y_end = y.replace(hour=23, minute=59, second=59, microsecond=999999)
            ts_start = int(y_start.timestamp())
            ts_end = int(y_end.timestamp())
            df = df[(df["timestamp"] >= ts_start) & (df["timestamp"] <= ts_end)]
        elif time_type == 1:
            # 今日 00:00:00 ~ 現在 (台北)
            t_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            ts_start = int(t_start.timestamp())
            ts_end = int(now.timestamp())
            df = df[(df["timestamp"] >= ts_start) & (df["timestamp"] <= ts_end)]
        elif time_type == 2:
            # 近 n 日 (含今日)
            n_start = (now - timedelta(days=n_days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
            ts_start = int(n_start.timestamp())
            ts_end = int(now.timestamp())
            df = df[(df["timestamp"] >= ts_start) & (df["timestamp"] <= ts_end)]

        # 關鍵字過濾
        if query:
            df = df[df["content"].astype(str).str.contains(query, case=False, na=False)]
        # tags 過濾（假設 tag 欄位存在於 info）
        if tags and tags != ["All"]:
            df = df[df["tag"].isin(tags)]

        # timestamp 轉換
        if "timestamp" in df.columns:
            df["發文時間"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert('Asia/Taipei').dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            df["發文時間"] = ""

        # 欄位 rename
        df["Id"] = df["doc_id"]
        df["KOL"] = df["kol_name"].fillna(df["kol_id"])
        df["連結"] = df["post_url"]
        df["內容"] = df["content"]
        df["互動數"] = df["reaction_count"]
        df["分享數"] = df["share_count"]

        result = df[["Id", "KOL", "連結", "內容", "互動數", "分享數", "發文時間"]].to_dict(orient="records")
        return JSONResponse({"kol_data": result})
    except Exception as e:
        logger.error(f"KOL data 過濾/合併出錯: {str(e)}")
        return JSONResponse({"kol_data": [], "error": str(e)}, status_code=500)

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
