import time
import uuid
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Body, Query
from .redis import set_redis_key, get_redis_key, delete_redis_key, scan_redis_keys, get_redis_connection
from .utils import logger
from .settings import SESSION_EXPIRE, GEMINI_MODEL, GEMINI_API_KEY
from .sheet import sheet_manager
import threading
from datetime import datetime
import google.generativeai as genai
from google.generativeai import GenerativeModel

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
    result = create_message(
        session_id, 
        search_id, 
        message.get("role"), 
        message.get("content")
    )
    return result

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
        None   # 不更新 role
    )}

@router.delete("/message")
async def api_delete_message(
    session_id: str,
    search_id: int,
    message_id: Optional[int] = None
):
    if message_id is not None:
        return {"success": delete_message(session_id, search_id, message_id)}
    # 沒有帶 message_id，直接清空該 search_id 的所有訊息
    from .redis import set_redis_key
    from .settings import SESSION_EXPIRE
    message_key = f"messages:{session_id}-{search_id}"
    set_redis_key(message_key, [], expire=SESSION_EXPIRE)
    logger.info(f"清空所有訊息 in {session_id}-{search_id}")
    return {"success": True}

# 新增 saved_search CRUD API
@router.post("/saved_search")
async def api_create_saved_search(
    session_id: str = Query(...),
    search_data: dict = Body(...)
):
    return create_saved_search(session_id, search_data)

@router.get("/saved_search")
async def api_get_saved_searches(session_id: str):
    return get_saved_searches(session_id)

@router.patch("/saved_search")
async def api_update_saved_search(
    session_id: str = Query(...),
    search_id: int = Query(...),
    update_data: dict = Body(...)
):
    updated_search = update_saved_search(session_id, search_id, update_data)
    if updated_search:
        return updated_search
    return {"error": "not found or update failed"}

@router.delete("/saved_search")
async def api_delete_saved_search(session_id: str, search_id: int):
    return {"success": delete_saved_search(session_id, search_id)}

# @router.get("/message/llm")
# async def api_get_llm_response(
#     session_id: str,
#     search_id: int,
#     query: str = Query(..., description="用戶查詢")
# ):
#     """
#     獲取 LLM 對用戶查詢的回應，基於前 30 個對話記錄
    
#     Args:
#         session_id: 會話 ID
#         search_id: 搜索 ID
#         query: 用戶查詢
        
#     Returns:
#         LLM 生成的回應消息內容
#     """
#     try:
#         # 創建用戶消息
#         # create_message(
#         #     session_id=session_id,
#         #     search_id=search_id,
#         #     role="user",
#         #     content=query
#         # )
        
#         # 使用延遲導入避免循環導入
#         from .gemini import gemini_chat
        
#         # 使用 Gemini API 處理請求，不再傳入 query
#         bot_reply = gemini_chat(session_id, search_id, query=query)
        
#         # 添加機器人回應到會話
#         # create_message(
#         #     session_id=session_id,
#         #     search_id=search_id,
#         #     role="bot",
#         #     content=bot_reply
#         # )
        
#         # 只返回內容，不需要其他元數據
#         return {"content": bot_reply}
#     except Exception as e:
#         logger.error(f"LLM 處理查詢時出錯: {str(e)} | redis_alive={is_redis_alive()}")
#         return {"error": str(e)}


@router.post("/message/llm")
async def api_post_llm_response(
    session_id: str = Query(..., description="會話 ID"),
    search_id: int = Query(..., description="搜索 ID"),
    request_data: dict = Body(..., description="請求內容，包含 query 字段")
):
    """
    通過 POST 方法獲取 LLM 對用戶查詢的回應，基於前 30 個對話記錄
    
    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        request_data: 請求內容，包含用戶查詢
        
    Returns:
        LLM 生成的回應消息內容
    """
    try:
        query = request_data.get("query", "")
        if not query:
            return {"error": "請求必須包含 query 字段"}
            
        # 使用延遲導入避免循環導入
        from .gemini import gemini_chat
        
        # 使用 Gemini API 處理請求
        bot_reply = gemini_chat(session_id, search_id, query=query)
        
        # 只返回內容，不需要其他元數據
        return {"content": bot_reply}
    except Exception as e:
        error_msg = f"LLM 處理 POST 查詢時出錯: {str(e)} | redis_alive={is_redis_alive()}"
        logger.error(error_msg)
        return {"error": str(e)}


@router.post("/message/kol-data-llm")
async def api_get_kol_data_llm_response(
    session_id: str = Query(...),
    search_id: int = Query(...),
    request_data: dict = Body(...),
):
    """
    從 Redis 中獲取 kol_data_md:{session_id}-{search_id} 的 Markdown 格式資料，
    並使用使用者的查詢和 prompt.txt 來產生 LLM 回應
    
    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        request_data: 包含查詢的請求體 {"query": "..."}
        
    Returns:
        LLM 生成的回應內容
    """
    try:
        # 從請求體中獲取查詢
        query = request_data.get("query", "")
        if not query:
            return {"error": "查詢不能為空"}
        
        # 從 Redis 中獲取 Markdown 格式的 KOL 數據
        from .redis import get_redis_key
        
        # 直接獲取 Markdown 格式數據
        kol_data_md_key = f"kol_data_md:{session_id}-{search_id}"
        markdown_content = get_redis_key(kol_data_md_key, default="")
        
        if not markdown_content:
            return {"error": "找不到 KOL 數據，請先使用 /api/redis/kol-data 獲取資料"}
        
        # 加載 prompt 模板
        from .gemini import load_prompt
        prompt = load_prompt()
        if not prompt:
            return {"error": "無法加載 prompt 模板"}
        
        # 直接使用 GenerativeModel 而不是 gemini_chat
        if not GEMINI_API_KEY:
            return {"error": "未設置 Gemini API 金鑰，無法使用聊天功能"}
            
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = GenerativeModel(GEMINI_MODEL)
            
            # 將 prompt 和 markdown 資料放入 history 中
            # 這樣 LLM 就能理解背景和數據，而用戶查詢可以更簡潔
            
            # 建立對話，將系統訊息放入 history
            chat = model.start_chat(
                history=[
                    {
                        "role": "user",
                        "parts": [prompt]
                    },
                    {
                        "role": "model",
                        "parts": [f"以下是 KOL 發文資料：\n\n```markdown\n{markdown_content}\n```"]
                    }
                ]
            )
            
            # 只傳送用戶的實際查詢
            response = chat.send_message(query)
            
            # 直接返回 LLM 的回應
            return {"content": response.text}
        except Exception as e:
            logger.error(f"Gemini API 呼叫出錯: {str(e)}")
            return {"error": f"Gemini API 錯誤: {str(e)}"}
            
    except Exception as e:
        logger.error(f"KOL data LLM 處理查詢時出錯: {str(e)}")
        return {"error": str(e)}

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
        
        # 獲取系統搜索，如果沒有則創建默認搜索
        global_saved_searches = get_redis_key("sheet:saved_searches", default=[])
        system_searches = [s for s in global_saved_searches if s.get("account") == "系統"]
        
        # 如果系統搜索為空，創建至少一個默認系統搜索
        if not system_searches:
            logger.warning("沒有找到系統搜索，使用默認系統搜索")
            _ = sheet_manager.get_kol_info(force_refresh=True)
            _ = sheet_manager.get_saved_searches(force_refresh=True)
            _ = sheet_manager.get_kol_data(force_refresh=True)

            # system_searches = [{
            #     "id": 1,
            #     "title": "預設搜索",
            #     "account": "系統",
            #     "order": 1,
            #     "query": {
            #         "title": "預設搜索",
            #         "time": 7,
            #         "source": 0,
            #         "tags": ["All"],
            #         "query": "",
            #         "n": 10,
            #         "range": None
            #     },
            #     "created_at": datetime.now().isoformat()
            # }]
            global_saved_searches = get_redis_key("sheet:saved_searches", default=[])
            system_searches = [s for s in global_saved_searches if s.get("account") == "系統"]

            # 寫回 redis 以便其它用戶使用
            set_redis_key("sheet:saved_searches", system_searches)
            logger.info("已創建默認系統搜索")
        
        session_data = {
            "created_at": now,
            "updated_at": now
        }
        session_key = f"sessions:{session_id}"
        set_redis_key(session_key, session_data, expire=SESSION_EXPIRE)
        saved_searches_key = f"saved_searches:{session_id}"
        set_redis_key(saved_searches_key, system_searches, expire=SESSION_EXPIRE)
        
        # 為每個 search_id 建立空的 messages key
        for search in system_searches:
            search_id = search.get("id")
            if search_id is not None:
                set_redis_key(f"messages:{session_id}-{search_id}", [], expire=SESSION_EXPIRE)
        
        # 建立一個 messages:{session_id}-999 的空 list
        set_redis_key(f"messages:{session_id}-999", [], expire=SESSION_EXPIRE)
        logger.info(f"創建新會話: {session_id}，複製了 {len(system_searches)} 筆系統搜索")
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
    content: str
) -> Dict[str, Any]:
    """添加消息到會話

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        role: 消息角色 ("user" 或 "bot")
        content: 消息內容

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
                "created_at": int(time.time()),
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
    role: Optional[str] = None
) -> bool:
    """更新指定 message_id 的訊息內容

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID
        message_id: 要更新的訊息 ID（int）
        content: 新內容（可選）
        role: 新角色（可選，但實際上不被使用）
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
                    # role 不會被更新
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
    search_data: Dict[str, Any],
    name: Optional[str] = None
) -> Dict[str, Any]:
    """保存搜索參數，格式與 get_saved_searches 一致"""
    try:
        lock = get_session_lock(session_id)
        with lock:
            session_data = get_session(session_id)
            if session_data is None:
                session_id = create_session(session_id)
                session_data = get_session(session_id)
            saved_searches_key = f"saved_searches:{session_id}"
            saved_searches = get_redis_key(saved_searches_key, default=[])
            search_id = max([s.get("id", 0) for s in saved_searches], default=0) + 1
            now_iso = datetime.now().isoformat()
            # 直接組裝 search dict，query 欄位要包進去
            search_record = {
                "id": search_id,
                "title": search_data.get("title", name or f"Search {int(time.time())}"),
                "account": search_data.get("account", "使用者"),
                "order": len(saved_searches) + 1,
                "query": {
                    "title": search_data.get("title", ""),
                    "time": search_data.get("time", 0),
                    "source": search_data.get("source", 0),
                    "tags": search_data.get("tags", []),
                    "query": search_data.get("query", ""),
                    "n": search_data.get("n", ""),
                    "range": search_data.get("range")
                },
                "created_at": now_iso
            }
            saved_searches.append(search_record)
            set_redis_key(saved_searches_key, saved_searches, expire=SESSION_EXPIRE)
            logger.info(f"保存搜索 {search_id} 到會話 {session_id}")
            return search_record
    except Exception as e:
        logger.error(f"保存搜索時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return {}


def get_saved_searches(session_id: str) -> List[Dict[str, Any]]:
    """獲取已保存的搜索列表，確保格式統一"""
    try:
        # 確保 session 存在，如果不存在就創建
        session = get_session(session_id)
        if not session:
            session_id = create_session(session_id)
            if not session_id:
                logger.error("創建 session 失敗")
                return []
            
        # 取得 saved_searches，如果是空的就複製系統搜索
        saved_searches_key = f"saved_searches:{session_id}"
        raw_list = get_redis_key(saved_searches_key, default=[])

        # 如果是空的，嘗試從全局複製系統搜索
        if len(raw_list) == 0:
            logger.info(f"saved_searches:{session_id} 為空，從全局複製系統搜索")
            global_saved_searches = get_redis_key("sheet:saved_searches", default=[])
            system_searches = [s for s in global_saved_searches if s.get("account") == "系統"]
            
            # 如果全局系統搜索仍為空，創建一個默認系統搜索
            if not system_searches:
                logger.warning("沒有找到系統搜索，使用默認系統搜索")
                _ = sheet_manager.get_kol_info(force_refresh=True)
                _ = sheet_manager.get_saved_searches(force_refresh=True)
                _ = sheet_manager.get_kol_data(force_refresh=True)

                # system_searches = [{
                #     "id": 1,
                #     "title": "預設搜索",
                #     "account": "系統",
                #     "order": 1,
                #     "query": {
                #         "title": "預設搜索",
                #         "time": 7,
                #         "source": 0,
                #         "tags": ["All"],
                #         "query": "",
                #         "n": 10,
                #         "range": None
                #     },
                #     "created_at": datetime.now().isoformat()
                # }]
                global_saved_searches = get_redis_key("sheet:saved_searches", default=[])
                system_searches = [s for s in global_saved_searches if s.get("account") == "系統"]
            
            set_redis_key(saved_searches_key, system_searches, expire=SESSION_EXPIRE)
            raw_list = system_searches
            logger.info(f"複製了 {len(raw_list)} 筆系統搜索")

        result = []
        for s in raw_list:
            # 如果已經是正確格式就直接用
            if all(k in s for k in ("id", "title", "account", "order", "query", "created_at")):
                result.append(s)

        return result
    except Exception as e:
        logger.error(f"獲取已保存搜索時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return []


def update_saved_search(
    session_id: str,
    search_id: int,
    update_data: dict
) -> dict:
    """
    更新已保存的搜索，直接覆蓋 search dict 的欄位，並回傳更新後的 search dict
    """
    try:
        lock = get_session_lock(session_id)
        with lock:
            if get_session(session_id) is None:
                return {}
            saved_searches_key = f"saved_searches:{session_id}"
            saved_searches = get_redis_key(saved_searches_key, default=[])
            updated = False
            updated_search = None
            for s in saved_searches:
                if s["id"] == search_id:
                    # 先處理 query 欄位的扁平 merge
                    if "query" in s and isinstance(s["query"], dict):
                        for key in ["title", "time", "source", "tags", "query", "n", "range"]:
                            if key in update_data:
                                s["query"][key] = update_data[key]
                    # 其他欄位照舊
                    for k in ["title", "account", "order", "created_at"]:
                        if k in update_data:
                            s[k] = update_data[k]
                    # 如果有 query 整包，還是可以直接覆蓋
                    if "query" in update_data and isinstance(update_data["query"], dict):
                        s["query"] = update_data["query"]
                    updated = True
                    updated_search = s
                    break
            if updated:
                set_redis_key(saved_searches_key, saved_searches, expire=SESSION_EXPIRE)
                logger.info(f"更新 saved_search {search_id} in {session_id}")
                return updated_search
            return {}
    except Exception as e:
        logger.error(f"更新 saved_search 時出錯: {str(e)} | redis_alive={is_redis_alive()}")
        return {}

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

# 為了向後兼容，保留原有的函數名稱
add_message = create_message