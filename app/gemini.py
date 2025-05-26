import google.generativeai as genai
from google.generativeai import GenerativeModel
import os

from fastapi import APIRouter

# 避免循環導入
from . import session
from .utils import logger
from .settings import GEMINI_MODEL, GEMINI_API_KEY

router = APIRouter()


def load_prompt(prompt_path="app/prompt.txt"):
    """
    讀取 prompt 文件內容
    
    Args:
        prompt_path: prompt 文件路徑
        
    Returns:
        prompt 內容文本，如果讀取失敗則返回 None
    """
    try:
        if not os.path.exists(prompt_path):
            logger.warning(f"Prompt 文件不存在: {prompt_path}")
            return None
            
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"讀取 prompt 文件失敗: {str(e)}")
        return None


def gemini_chat(session_id: str = "default", search_id: int = 999, prompt_path: str = "app/prompt.txt", query: str = None) -> str:
    """
    使用 Gemini API 進行聊天，根據會話歷史生成回應

    Args:
        session_id: 會話 ID
        search_id: 搜索 ID，默認為 999 (主對話)
        prompt_path: prompt 文件路徑，默認為 app/prompt.txt
        query: 若有值則直接用 query 當成 send_message 內容

    Returns:
        AI 回應文本
    """
    api_key = GEMINI_API_KEY
    if not api_key:
        error_msg = "錯誤：未設置 Gemini API 金鑰，無法使用聊天功能。"
        error_msg += "請在環境變數中設置 GEMINI_API_KEY。"
        return error_msg

    try:
        genai.configure(api_key=api_key)
        model = GenerativeModel(GEMINI_MODEL)
        messages = session.get_messages(session_id, search_id, limit=30)
        if not messages and not query:
            return "請輸入您的問題或指令。"
        prompt = load_prompt(prompt_path)
        context = []
        if prompt:
            context.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })
        # 有 query 時 context 只加 messages[:-1]
        if query:
            for msg in messages[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                context.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
        else:
            for msg in messages[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                context.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
        chat = model.start_chat(
            history=context if context else None
        )
        # 如果有 query 直接用 query，否則用最新一筆
        send_content = query if query else messages[-1]["content"]
        response = chat.send_message(send_content)
        return response.text
    except Exception as e:
        logger.error(f"Gemini 聊天出錯: {str(e)}")
        return f"Gemini API 錯誤: {str(e)}"


# 以下函數未在技術文件中提及，暫時註釋掉
"""
@router.post("/chat/ai")
async def chat_ai(request: Request):
    # 處理 AI 聊天請求，自動讀取會話歷史並生成回應
    
    # 請求格式：
    # {
    #     "message": "用戶輸入的消息",
    #     "session_id": "會話ID" (可選)
    # }
    try:
        req_data = await request.json()
        message = req_data.get("message", "").strip()
        session_id = req_data.get("session_id", "default")

        logger.info(f"收到 AI 聊天請求 (session_id: {session_id})")

        # 確保消息不為空
        if not message:
            logger.error("錯誤: 消息為空")
            return JSONResponse({"error": "消息不能為空"}, status_code=400)

        logger.info(f"用戶輸入: {message[:50]}...")

        # 添加用戶消息到會話
        user_message = add_message(
            session_id=session_id,
            role="user",
            content=message
        )

        # 使用 gemini_chat 處理請求
        bot_reply = gemini_chat(message, session_id)

        # 添加機器人回應到會話
        bot_message = add_message(
            session_id=session_id,
            role="bot",
            content=bot_reply
        )

        # 返回響應
        return JSONResponse({
            "reply": bot_reply,
            "user_message_id": user_message["id"],
            "bot_message_id": bot_message["id"]
        })

    except Exception as e:
        logger.error(f"處理 AI 聊天請求時出錯: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/chat/direct")
async def chat_direct(request: Request):
    # 直接添加訊息到聊天界面，不通過 LLM
    
    # 請求格式：
    # {
    #     "role": "user" | "bot",
    #     "content": "訊息內容",
    #     "session_id": "用戶的會話ID" (可選),
    #     "metadata": { ... } (可選)
    # }
    try:
        req_data = await request.json()
        role = req_data.get("role")
        content = req_data.get("content")
        session_id = req_data.get("session_id", "default")
        metadata = req_data.get("metadata", {})

        if role not in ["user", "bot"]:
            return JSONResponse(
                {"error": "role 必須是 'user' 或 'bot'"},
                status_code=400
            )

        if not content:
            return JSONResponse(
                {"error": "content 不能為空"},
                status_code=400
            )

        # 添加消息到會話
        message = add_message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata
        )

        return JSONResponse({
            "status": "success",
            "message_id": message["id"]
        })

    except Exception as e:
        logger.error(f"直接添加消息時出錯: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/chat/batch")
async def chat_batch(request: Request):
    # 批量添加消息到會話
    
    # 請求格式：
    # {
    #     "messages": [
    #         {"role": "user", "content": "用戶消息1"},
    #         {"role": "bot", "content": "機器人回應1"},
    #         ...
    #     ],
    #     "session_id": "會話ID" (可選)
    # }
    try:
        req_data = await request.json()
        messages = req_data.get("messages", [])
        session_id = req_data.get("session_id", "default")

        if not messages:
            return JSONResponse(
                {"error": "messages 不能為空"},
                status_code=400
            )

        # 批量添加消息
        message_ids = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            metadata = msg.get("metadata", {})

            if role not in ["user", "bot"]:
                continue

            if not content:
                continue

            # 添加消息
            message = add_message(
                session_id=session_id,
                role=role,
                content=content,
                metadata=metadata
            )
            message_ids.append(message["id"])

        return JSONResponse({
            "status": "success",
            "message_ids": message_ids,
            "count": len(message_ids)
        })

    except Exception as e:
        logger.error(f"批量添加消息時出錯: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500) 
""" 