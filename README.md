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


1. 啟動時（預熱緩存）
    sheet:kol_data：KOL 數據（Google Sheet 來的，for 查詢）
    sheet:kol_info：KOL 基本資料（Google Sheet 來的，for 下拉選單等）
    sheet:saved_searches：全局已保存搜索（Google Sheet 來的，for 全局查詢/展示）

    這三個 key 只跟 Google Sheet 有關，跟 session 無關，通常是全局緩存。

    1.1 sheet:kol_data 範例 data
    [
        {
            "doc_id": "123",
            "kol_id": "kol_001",
            "timestamp": 1710000000,
            "post_url": "https://...",
            "content": "貼文內容",
            "reaction_count": 100,
            "share_count": 10
        },
        ...
    ]
    備註：在 google sheet 上，該 tab 的欄位是：doc_id	tag_names	kol_id	kol_name	timestamp	post_url	content	reaction_count	share_count

    1.2 sheet:kol_data 範例 data
    [
        {
            "kol_id": "kol_001",
            "kol_name": "小明",
            "url": "https://...",
            "tag": "美食"
        },
        ...
    ]
    備註：在 google sheet 上，該 tab 的欄位是：KOL url tag kol_id ，KOL 就是 redis 裡的 kol_name

    1.3 sheet:saved_searches 範例 data
    [
        {
            "id": 1,
            "title": "美食搜尋",
            "account": "系統",
            "order": 1,
            "query": {
                "title": "美食",
                "time": 30,
                "source": 0,
                "tags": ["美食", "餐廳"],
                "query": "壽司",
                "n": 10,
                "range": [1700000000, 1710000000]
            },
            "created_at": "2024-03-01 12:00:00"
        },
        ...
    ]
    備註：在 google sheet 上，該 tab 的欄位是：id 標題 帳號 順序 查詢值 新增時間

2. 用戶互動時（每個 session 會有獨立 key）
    假設 session_id = abc123：
        - sessions:abc123：session 基本資料（created_at, updated_at）
        - messages:abc123-1：該 session、該 search_id 的所有訊息（list of message dicts）
        - saved_searches:abc123：該 session 的 saved search（list of search dicts）

    每次 init 時，新增 sessions:{session_id} 後，再新增 saved_searches:{session_id} 這個就是從 sheet:saved_searches 的 account == "系統" 複製過來。假設複製了 4 個過來，那就要產生相對應的 messages:{session_id}-{search_id} （有4個就產生4個空的）
    同時生成一個 messages:{session_id}-999 的空的 key，這個 msg key 代表入口網站的對話紀錄
    
    2.1 session:abc123 範例 data
    {
        "created_at": 1711000000,
        "updated_at": 1711000050,
    }
    
    2.2 message:abc123 範例 data
    [
        {
            "id": "1711000000123_1",
            "role": "bot",
            "content": "歡迎使用！我是您的 AI 助手，有什麼我可以幫您的嗎？",
            "timestamp": 1711000000,
            "metadata": {}
        },
        ...
    ]

    2.3 saved_searches:abc123 範例 data
    這個格式就是要跟 sheet:saved_searches 的格式一樣
    [
        {
            "id": 1,
            "title": "美食搜尋",
            "account": "系統",
            "order": 1,
            "query": {
                "title": "美食",
                "time": 30,
                "source": 0,
                "tags": ["美食", "餐廳"],
                "query": "壽司",
                "n": 10,
                "range": [1700000000, 1710000000]
            },
            "created_at": "2024-03-01 12:00:00"
        },
        ...
    ]

3. 後端提供給前端使用的 API

GET    /api/session
  Query: session_id (optional)
  說明：取得或創建 session

DELETE /api/session
  Query: session_id (required)
  說明：刪除 session 及其所有資料

POST   /api/message
  Query: session_id (required), search_id (required)
  Body:  { "role": "user|bot", "content": str, "metadata": dict (optional) }
  說明：新增訊息

GET    /api/message
  Query: session_id (required), search_id (required), since_id (optional), limit (optional)
  說明：取得訊息列表

PATCH  /api/message
  Query: session_id (required), search_id (required), message_id (required)
  Body:  { "content": str (optional), "role": str (optional), "metadata": dict (optional) }
  說明：更新訊息

DELETE /api/message
  Query: session_id (required), search_id (required), message_id (required)
  說明：刪除訊息

POST   /api/saved_search
  Query: session_id (required)
  Body 範例: {
        "title": "[系統] 今日日戰報",
        "time": 1,
        "source": 0,
        "tags": [
            "All"
        ],
        "query": "...",
        "n": "",
        "range": null
    }
  說明：新增 saved_search

  Response 範例: {
        "id": 1,
        "title": "[系統] 今日日戰報",
        "account": "系統",
        "order": 1,
        "query": {
            "title": "[系統] 今日日戰報",
            "time": 1,
            "source": 0,
            "tags": [
            "All"
            ],
            "query": "...",
            "n": "",
            "range": null
        },
        "created_at": "2025-05-17T02:19:00.325556"
    }

GET    /api/saved_search
  Query: session_id (required)
  說明：取得 saved_search 列表

  Response 範例:
    [
        {
            "id": 1,
            "title": "[系統] 今日日戰報",
            "account": "系統",
            "order": 1,
            "query": {
                "title": "[系統] 今日日戰報",
                "time": 1,
                "source": 0,
                "tags": [
                "All"
                ],
                "query": "...",
                "n": "",
                "range": null
            },
            "created_at": "2025-05-17T02:19:00.325556"
        },
        ...
    ]


PATCH  /api/saved_search
  Query: session_id (required), search_id (required)
  Body 範例:  {
        "title": "[系統] 今日日戰報",
        "time": 1,
        "source": 0,
        "tags": [
            "All"
        ],
        "query": "...",
        "n": "",
        "range": null
    }
  說明：更新 saved_search
  Response 範例: {
        "id": 1,
        "title": "[系統] 今日日戰報",
        "account": "系統",
        "order": 1,
        "query": {
            "title": "[系統] 今日日戰報",
            "time": 1,
            "source": 0,
            "tags": [
            "All"
            ],
            "query": "...",
            "n": "",
            "range": null
        },
        "created_at": "2025-05-17T02:19:00.325556"
    }

DELETE /api/saved_search
  Query: session_id (required), search_id (required)
  說明：刪除 saved_search


GET    /api/sheet/kol-list
  說明：取得所有 KOL 列表

GET    /api/sheet/saved-searches
  說明：取得全局 saved_searches

GET    /api/redis/kol-info
  說明：取得全局 KOL info

GET    /api/redis/kol-data
  說明：取得全局 KOL data

GET    /ping
  說明：健康檢查



--------------------------------

UI 前端行為說明

後端的 domain 被定義成 REACT_APP_API_URL 變數，每次 request 時要帶上 API KEY

Saved Search List 與 Session/快取行為說明
1. SessionId 管理
    每個使用者（以 browser 為單位）首次開啟網頁時，前端會檢查 sessionStorage 是否已有 sessionId。
    - 若有，直接使用該 sessionId。
    - 若無，會向後端 GET /api/session 申請新的 sessionId，並存入 sessionStorage。
    這樣設計可確保同一個 user/browser reload 頁面時，sessionId 不會改變，所有 saved search、訊息等資料都能正確對應同一個 session。

2. Saved Search List 的 client 快取
    - 前端根據目前的 sessionId，向後端查詢該 session 的 saved searches（GET /api/saved_search?session_id=...），並將結果存入 React state。

3. API 呼叫時機
    - 產生/取得 sessionId
        頁面初始化時，若 sessionStorage 沒有 session_id，call GET /api/session 取得，並存入 sessionStorage。
    - 取得 saved searches
        SavedSearchList 初始化或點擊「刷新列表」時，call GET /api/saved_search?session_id=...，結果存進前端 state。
    - 新增 saved search
        使用者新增時，call POST /api/saved_search?session_id=...，body 為 search 資料，回傳後更新 state。
    - 刪除 saved search
        使用者刪除時，call DELETE /api/saved_search?session_id=...&search_id=...，回傳後從 state 移除。
    - 編輯 saved search
        使用者編輯時，call PATCH /api/saved_search?session_id=...&search_id=...，回傳後更新 state。
    - 清空列表 
        點擊「清空列表」時，獲得所有非”系統”的 search_id，loop call DELETE /api/saved_search?session_id=...&search_id=...，回傳後 state 只保留系統預設。

4. UI 資料流與互動
    - 當使用者點擊「刷新列表」時，會強制重新向後端拉取最新的 saved searches，並更新前端 state 與 UI。
    - 當使用者點擊「清空列表」時，會呼叫後端 API 清空該 session 的 saved searches，前端 state 也會同步更新，UI 只保留系統預設的搜尋條件。
    - 所有的增刪改查操作都會即時更新前端 state，並同步到 UI，確保操作即時反映。
5. 排序與顯示
    - Saved Search List 會根據 account 分組（系統預設的排最前面），同組內依 order 排序，確保 UI 呈現與後端資料一致。
    - 拖曳排序、刪除、編輯等操作都會即時反映在前端 state 與 UI。
    - 拖曳完成後，要重新更新 redis 與 state 的 "排序" 欄位，

SearchModal 行為說明
1. 新增搜索
    - 觸發：點 Sidebar「新增搜索」按鈕，彈出 SearchModal。
    - 取消：點「取消」按鈕或 modal 背景，直接關閉 SearchModal，不會送出任何資料。
    - 儲存：
        - 驗證：
            - 標題（title）必填，空值會顯示紅字錯誤提示。
            - 若選「近N日」，N 必須為 1~30 的整數，否則顯示紅字錯誤提示。
            - 其它時間選項不需填 N。
        - 自訂區間（時間選「自訂區間」）：
            - RangePicker 直接 disabled，無法點擊。
            - 滑鼠移上去會顯示 Tooltip：「功能還在開發中」。
        - 來源（source）：
            - 「Threads」選項 disabled，無法點擊。
            - 滑鼠移上去會顯示 Tooltip：「功能還在開發中」。
        - KOL：
            - 下拉選單預設選「All」。
            - 「All」不是原始 tag，僅作為 UI default。
            - 可多選/自訂輸入 KOL，chip 方式顯示，可點叉移除。
            - 若 chip 全部移除，會自動回到「All」。
        - API：
            - 通過 POST /api/saved_search?session_id=... 新增，並呼叫 POST /api/message?session_id=...&search_id=... 新增空的訊息。
            - 傳送資料：title、account: "使用者"、order: 99（實際 order 由後端決定）、query（含所有查詢條件）。
            - 後端自動分配 id（全域唯一遞增）、order（同 account 下遞增）、createdAt。
        - state：
            - 新增成功後，前端自動更新本地 state ，立即反映 UI。
        - 關閉：儲存成功自動關閉 SearchModal。
2. 編輯搜索
    - 觸發：點「編輯」按鈕，彈出 SearchModal。
    - 初始值：所有欄位自動帶入當前搜索的 state/cache 值。
    - 儲存：
        - 驗證規則同「新增」。
        - 通過 PATCH /api/saved_search?session_id=...&search_id=... 更新。
        - 只會更新 title/query，不會動到 id/account/order。
        - 成功後自動更新本地 state，UI 立即反映。
        - 儲存成功自動關閉 SearchModal。
3. 閱覽（View）
    - 觸發：點「閱覽」或右鍵選單「檢視」，彈出 SearchModal。
    - 初始值：所有欄位自動帶入當前搜索的 state 值。
    - UI：
        - 所有欄位 disabled，無法編輯。
        - 沒有「儲存」按鈕，僅有「關閉」。
        - 不能觸發任何 API。
4. KOL 下拉選單
    - 元件：TagSelector（MUI Autocomplete + Chip）
    - 預設：value=["All"]，All 不是原始 tag。
    - 行為：
        - 可多選/自訂輸入 KOL。 
        - chip 方式顯示，可點叉移除。
        - chip 全部移除時自動回到「All」。
        - disabled 狀態時不可互動。
5. 來源（source）Threads 選項
    - UI：Threads 按鈕 disabled。   
    - UX：滑鼠移上去顯示 Tooltip：「功能還在開發中」。
    - 行為：無法點擊、無法選取。
6. 其它補充
    - id/order/account：
        - id：全域唯一遞增（由後端分配）。
        - account：固定 "使用者"。
        - order：同一 account 下遞增（由後端分配）。
    - state/cache：所有操作（新增、編輯、刪除、排序）都會同步更新本地 state 及 cache，確保 UI 實時反映。
    - API error 處理：失敗時會顯示錯誤訊息於 console，UI 不會卡死。



----

ChatPage 行為說明

入口頁面，該頁面只有剛進入此頁面時才會出現的的歡迎訊息
頁面呈現內容：
歡迎使用 AI 雷達站！
您可以透過以下方式開始使用：
1. 從左側選擇已保存的搜索條件
2. 獲取篩選過的 KOL 數據
3. 與 AI 助手互動分析數據

若點選了左側的任何一個查詢





          `嗨！我找到了「${title}」的搜索資料啦！🎯✨`,
          `這批資料的時間範圍是 ${formatTime(result.start_time)} ~ ${formatTime(result.end_time)} 📅`,
          `我已經幫你整理好了：💁 資料來源：${result.source || '全部'} 📊 涵蓋KOL：${result.kol || 'All'} ⭐`,
          `總共有 ${result.records.length} 筆資料等著你來探索！👀`,
          `有什麼想過濾的嗎？我很樂意幫你找出這段時間的趨勢喔！`


-----

streamlit component 發布後， streamlit app developer 我希望如下使用
```
import json
import tempfile
import streamlit as st
import st_llm_search_engine as st_llm


st.set_page_config(
    page_title="LLM Search Engine Demo (UAT)",
    page_icon="🔍",
    layout="collapsed",
    initial_sidebar_state="auto",
)

# 隱藏Streamlit默認UI元素
hide_st_style = """
<style>
    /* 隱藏Streamlit默認UI元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* 確保容器填滿整個視窗 */
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        width: 100vw !important;
    }

    /* 確保應用填滿整個視窗 */
    .stApp {
        margin: 0 !important;
        padding: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
    }

    /* 移除Streamlit容器的內邊距和外邊距 */
    [data-testid="stAppViewContainer"] {
        padding: 0 !important;
        margin: 0 !important;
    }
    [data-testid="stVerticalBlock"] {
        padding: 0 !important;
        margin: 0 !important;
        gap: 0 !important;
    }
    [data-testid="stHorizontalBlock"] {
        padding: 0 !important;
        margin: 0 !important;
        gap: 0 !important;
    }
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# 設置 Gemini API Key
api_rul = st.secrets["BACKEND_API_URL"]
api_key = st.secrets["BACKEND_API_KEY"]

st_llm.render(
    api_url=api_url,
    api_key=api_key
)
```