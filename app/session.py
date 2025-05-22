import time
import uuid
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Body, Query
from .redis import set_redis_key, get_redis_key, delete_redis_key, scan_redis_keys, get_redis_connection
from .utils import logger
from .settings import SESSION_EXPIRE
import threading

# per-session lock
_session_locks: Dict[str, threading.Lock] = {}
def get_session_lock(session_id: str) -> threading.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = threading.Lock()
    return _session_locks[session_id]

# 創建路由器
router = APIRouter()


@router.delete("/session")
async def delete_session_endpoint(session_id: str):
    """刪除會話及其相關數據"""
    try:
        ok = delete_session(session_id)
        if ok:
            logger.info(f"已刪除會話 {session_id} 的所有數據")
            return {"status": "success", "message": "會話已刪除"}
        else:
            return {"status": "error", "message": "會話不存在或刪除失敗"}
    except Exception as e:
        logger.error(f"刪除會話時出錯: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.get("/session")
async def get_or_create_session(session_id: Optional[str] = None):
    """獲取現有會話或創建新會話

    如果提供session_id且存在，則返回該會話
    如果提供session_id但不存在，則創建該session_id的會話
    如果未提供session_id，則創建新會話
    """
    try:
        if session_id:
            session = get_session(session_id)
            if session:
                return {"session_id": session_id, "session": session}
            else:
                new_id = create_session(session_id)
                session = get_session(new_id)
                return {"session_id": new_id, "session": session}
        else:
            new_id = create_session()
            session = get_session(new_id)
            return {"session_id": new_id, "session": session}
    except Exception as e:
        logger.error(f"獲取/創建會話時出錯: {str(e)}")
        return {"status": "error", "message": str(e)}

# 新增 message CRUD API
@router.post("/message")
async def api_create_message(
    session_id: str = Query(...),
    search_id: int = Query(...),
    message: dict = Body(...)
):
    return create_message(
        session_id, 
        search_id, 
        message.get("role"), 
        message.get("content"), 
        message.get("metadata")
    )

@router.get("/message")
async def api_get_messages(session_id: str, search_id: int, since_id: Optional[int] = None, limit: Optional[int] = None):
    return get_messages(session_id, search_id, since_id, limit)

@router.patch("/message")
async def api_update_message(
    session_id: str = Query(...),
    search_id: int = Query(...),
    message_id: int = Query(...),
    update_data: dict = Body(...)
):
    return {"success": update_message(
        session_id, 
        search_id, 
        message_id, 
        update_data.get("content"), 
        update_data.get("role"), 
        update_data.get("metadata")
    )}

@router.delete("/message")
async def api_delete_message(session_id: str, search_id: int, message_id: int):
    return {"success": delete_message(session_id, search_id, message_id)}

# 新增 saved_search CRUD API
@router.post("/saved_search")
async def api_create_saved_search(
    session_id: str = Query(...),
    search_params: dict = Body(...),
    name: Optional[str] = Body(None)
):
    return create_saved_search(session_id, search_params, name)

@router.get("/saved_search")
async def api_get_saved_searches(session_id: str):
    return get_saved_searches(session_id)

@router.patch("/saved_search")
async def api_update_saved_search(
    session_id: str = Query(...),
    search_id: int = Query(...),
    name: Optional[str] = Body(None),
    params: Optional[dict] = Body(None)
):
    return {"success": update_saved_search(session_id, search_id, name, params)}

@router.delete("/saved_search")
async def api_delete_saved_search(session_id: str, search_id: int):
    return {"success": delete_saved_search(session_id, search_id)}

def generate_session_id() -> str:
    """生成唯一的 session ID

    Returns:
        唯一的 session ID
    """
    return str(uuid.uuid4())


def create_session(session_id: Optional[str] = None) -> str:
    """創建新的會話

    Args:
        session_id: 指定的會話 ID，如果為 None 則自動生成

    Returns:
        會話 ID
    """
    try:
        if session_id is None:
            session_id = generate_session_id()
        now = int(time.time())
        global_saved_searches = get_redis_key("sheet:saved_searches", default=[])
        system_searches = [s for s in global_saved_searches if s.get("account") == "系統"]
        session_data = {
            "created_at": now,
            "updated_at": now
        }
        session_key = f"sessions:{session_id}"
        set_redis_key(session_key, session_data, expire=SESSION_EXPIRE)
        saved_searches_key = f"saved_searches:{session_id}"
        set_redis_key(saved_searches_key, system_searches, expire=SESSION_EXPIRE)
        logger.info(f"創建新會話: {session_id}")
        return session_id
    except Exception as e:
        logger.error(f"創建會話時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return ""

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """獲取會話數據

    Args:
        session_id: 會話 ID

    Returns:
        會話數據，如果不存在則返回 None
    """
    try:
        session_key = f"sessions:{session_id}"
        session_data = get_redis_key(session_key)
        if session_data is None:
            new_id = create_session(session_id)
            if new_id != session_id:
                return None
            return get_session(session_id)
        return session_data
    except Exception as e:
        logger.error(f"獲取會話時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return None


def delete_session(session_id: str) -> bool:
    """刪除會話

    Args:
        session_id: 會話 ID

    Returns:
        是否成功刪除
    """
    try:
        session_data = get_session(session_id)
        if session_data is None:
            return False
        session_key = f"sessions:{session_id}"
        delete_redis_key(session_key)
        keys = scan_redis_keys(f"messages:{session_id}-*")
        for k in keys:
            delete_redis_key(k)
        saved_searches_key = f"saved_searches:{session_id}"
        delete_redis_key(saved_searches_key)
        return True
    except Exception as e:
        logger.error(f"刪除會話時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return False


def create_message(
    session_id: str,
    search_id: int,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """添加消息到會話

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        role: 消息角色 ("user" 或 "bot")
        content: 消息內容
        metadata: 消息元數據 (可選)，用於存儲額外信息，如查詢參數或分析結果

    Returns:
        添加的消息對象
    """
    try:
        lock = get_session_lock(session_id)
        with lock:
            session_data = get_session(session_id)
            if session_data is None:
                session_id = create_session(session_id)
                session_data = get_session(session_id)
            message_key = f"messages:{session_id}-{search_id}"
            messages = get_redis_key(message_key, default=[])
            message_id = max([m["id"] for m in messages], default=-1) + 1
            message = {
                "id": message_id,
                "role": role,
                "content": content,
                "timestamp": int(time.time()),
                "metadata": metadata or {}
            }
            messages.append(message)
            set_redis_key(message_key, messages, expire=SESSION_EXPIRE)
            logger.info(f"添加消息 {message_id} 到會話 {session_id}")
            return message
    except Exception as e:
        logger.error(f"添加消息時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return {}


def get_messages(
    session_id: str,
    search_id: int,
    since_id: Optional[int] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """獲取會話消息

    Args:
        session_id: 會話 ID
        since_id: 只獲取此 ID 之後的消息
        limit: 消息數量限制

    Returns:
        消息列表
    """
    try:
        if get_session(session_id) is None:
            return []
        message_key = f"messages:{session_id}-{search_id}"
        messages = get_redis_key(message_key, default=[])
        if since_id is not None:
            messages = [msg for msg in messages if msg["id"] > since_id]
        if limit and limit > 0:
            messages = messages[-limit:]
        return messages
    except Exception as e:
        logger.error(f"獲取消息時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return []


def update_message(
    session_id: str,
    search_id: int,
    message_id: int,
    content: Optional[str] = None,
    role: Optional[str] = None,
    metadata: Optional[dict] = None
) -> bool:
    """更新指定 message_id 的訊息內容

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        message_id: 要更新的訊息 ID（int）
        content: 新內容（可選）
        role: 新角色（可選）
        metadata: 新 metadata（可選）
    Returns:
        是否成功更新
    """
    try:
        lock = get_session_lock(session_id)
        with lock:
            if get_session(session_id) is None:
                return False
            message_key = f"messages:{session_id}-{search_id}"
            messages = get_redis_key(message_key, default=[])
            updated = False
            for msg in messages:
                if msg["id"] == message_id:
                    if content is not None:
                        msg["content"] = content
                    if role is not None:
                        msg["role"] = role
                    if metadata is not None:
                        msg["metadata"] = metadata
                    updated = True
                    break
            if updated:
                set_redis_key(message_key, messages, expire=SESSION_EXPIRE)
                logger.info(f"更新消息 {message_id} in {session_id}-{search_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"更新消息時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return False


def delete_message(session_id: str, search_id: int, message_id: int) -> bool:
    """刪除單一訊息"""
    try:
        lock = get_session_lock(session_id)
        with lock:
            if get_session(session_id) is None:
                return False
            message_key = f"messages:{session_id}-{search_id}"
            messages = get_redis_key(message_key, default=[])
            new_messages = [msg for msg in messages if msg["id"] != message_id]
            if len(new_messages) == len(messages):
                return False  # 沒有刪除任何東西
            set_redis_key(message_key, new_messages, expire=SESSION_EXPIRE)
            logger.info(f"刪除消息 {message_id} in {session_id}-{search_id}")
            return True
    except Exception as e:
        logger.error(f"刪除消息時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return False


def create_saved_search(
    session_id: str,
    search_params: Dict[str, Any],
    name: Optional[str] = None
) -> Dict[str, Any]:
    """保存搜索參數

    Args:
        session_id: 會話 ID
        search_params: 搜索參數
        name: 搜索名稱 (可選)

    Returns:
        保存的搜索記錄
    """
    try:
        lock = get_session_lock(session_id)
        with lock:
            session_data = get_session(session_id)
            if session_data is None:
                session_id = create_session(session_id)
                session_data = get_session(session_id)
            saved_searches_key = f"saved_searches:{session_id}"
            saved_searches = get_redis_key(saved_searches_key, default=[])
            search_id = max([s["id"] for s in saved_searches], default=-1) + 1
            search_record = {
                "id": search_id,
                "name": name or f"Search {int(time.time())}",
                "params": search_params,
                "created_at": int(time.time()),
                "updated_at": int(time.time())
            }
            saved_searches.append(search_record)
            set_redis_key(saved_searches_key, saved_searches, expire=SESSION_EXPIRE)
            logger.info(f"保存搜索 {search_id} 到會話 {session_id}")
            return search_record
    except Exception as e:
        logger.error(f"保存搜索時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return {}


def get_saved_searches(session_id: str) -> List[Dict[str, Any]]:
    """獲取已保存的搜索列表

    Args:
        session_id: 會話 ID

    Returns:
        已保存的搜索列表
    """
    try:
        if get_session(session_id) is None:
            return []
        saved_searches_key = f"saved_searches:{session_id}"
        return get_redis_key(saved_searches_key, default=[])
    except Exception as e:
        logger.error(f"獲取已保存搜索時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return []


def update_saved_search(
    session_id: str,
    search_id: int,
    name: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None
) -> bool:
    """
    更新已保存的搜索

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        name: 新的名稱（可選）
        params: 新的參數（可選）

    Returns:
        是否成功更新
    """
    try:
        lock = get_session_lock(session_id)
        with lock:
            if get_session(session_id) is None:
                return False
            saved_searches_key = f"saved_searches:{session_id}"
            saved_searches = get_redis_key(saved_searches_key, default=[])
            updated = False
            for s in saved_searches:
                if s["id"] == search_id:
                    if name is not None:
                        s["name"] = name
                    if params is not None:
                        s["params"] = params
                    s["updated_at"] = int(time.time())
                    updated = True
                    break
            if updated:
                set_redis_key(saved_searches_key, saved_searches, expire=SESSION_EXPIRE)
                logger.info(f"更新 saved_search {search_id} in {session_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"更新 saved_search 時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return False

def delete_saved_search(session_id: str, search_id: int) -> bool:
    """刪除已保存的搜索

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID

    Returns:
        是否成功刪除
    """
    try:
        lock = get_session_lock(session_id)
        with lock:
            if get_session(session_id) is None:
                return False
            saved_searches_key = f"saved_searches:{session_id}"
            saved_searches = get_redis_key(saved_searches_key, default=[])
            filtered_searches = [s for s in saved_searches if s["id"] != search_id]
            if len(filtered_searches) == len(saved_searches):
                return False
            set_redis_key(saved_searches_key, filtered_searches, expire=SESSION_EXPIRE)
            logger.info(f"刪除搜索 {search_id} in {session_id}")
            return True
    except Exception as e:
        logger.error(f"刪除搜索時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return False

def is_redis_alive() -> bool:
    try:
        r = get_redis_connection()
        return r.ping() is True
    except Exception:
        return False