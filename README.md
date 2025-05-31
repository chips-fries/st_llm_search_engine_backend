## ST LLM Search Engine Backend

FastAPI + Redis + Google Sheet API server for LLM search engine.

* **適合部署到**: Render、Railway、Fly.io 等雲平台
* **依賴管理**: Poetry
* **功能支援**: Google Sheet, Gemini API, Redis（本地或 fakeredis）

---

## 1. 快速開始

### 1.1. 開發環境

```bash
# 安裝依賴
poetry install

# 啟動開發伺服器 (重新載入模式)
poetry run uvicorn app.app:app --reload --host 0.0.0.0 --port 10000
```

* 預設啟動後，後端在 `http://0.0.0.0:10000` 可連接。

### 1.2. Docker 部署

```bash
# 建置映像檔
docker build -t st-llm-backend .

# 啟動容器並對應到本機 10000 端口
docker run -p 10000:10000 st-llm-backend
```

### 1.3. Render 部署

1. 新增 Web Service。
2. **Start Command**: `poetry run uvicorn app.app:app --host 0.0.0.0 --port 10000`
3. **Port**: 10000
4. 在環境變數中設定 Google Sheet、Gemini API、Redis 等相關金鑰。

---

## 2. Redis 快取與資料結構

此後端使用 Redis 作為緩存層，主要區分兩大類 Key：全局緩存 (pre-load) 與使用者 session 緩存。

### 2.1. 啟動時 (預熱緩存)

以下三個 Key 只跟 Google Sheet 相關，且為全局共用 (與 Session 無關)：

1. `sheet:kol_data` (KOL 數據，用於查詢)
2. `sheet:kol_info` (KOL 基本資料，用於下拉選單)
3. `sheet:saved_searches` (全局已保存搜索，用於展示)

#### 範例資料

* **sheet\:kol\_data**

  ```json
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
  ```

  * Google Sheet 欄位順序：`doc_id, tag_names, kol_id, kol_name, timestamp, post_url, content, reaction_count, share_count`

* **sheet\:kol\_info**

  ```json
  [
    {
      "kol_id": "kol_001",
      "kol_name": "小明",
      "url": "https://...",
      "tag": "美食"
    },
    ...
  ]
  ```

  * Google Sheet 欄位順序：`KOL, url, tag, kol_id` (KOL 對應 redis 中的 `kol_name`)

* **sheet\:saved\_searches**

  ```json
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
  ```

  * Google Sheet 欄位順序：`id, 標題, 帳號, 順序, 查詢值, 新增時間`

### 2.2. 用戶互動時 (Session 專屬 Key)

每個新的使用者 Session (由後端分配 `session_id`) 都有專屬的 Redis Key：

* `sessions:{session_id}`: Session 基本資料 (含 `created_at`, `updated_at`)
* `messages:{session_id}-{search_id}`: 該 Session、該 saved search 所有訊息
* `saved_searches:{session_id}`: 該 Session 的 Saved Search 列表

#### 初始化流程

1. 當前端呼叫 `GET /api/session` 時，後端會分配新的 `session_id`。
2. 將 `sheet:saved_searches` 中 `account == "系統"` 的項目複製到 `saved_searches:{session_id}`。

   * 假設複製了 4 筆，就要為每個 search (含 `search_id`) 建立對應空的 `messages:{session_id}-{search_id}`。
   * 同時建立即 `messages:{session_id}-999` 作為入口網站對話紀錄。

##### 範例：Session 與訊息格式

* **sessions\:abc123**

  ```json
  {
    "created_at": 1711000000,
    "updated_at": 1711000050
  }
  ```

* **messages\:abc123-1**

  ```json
  [
    {
      "id": 1,
      "role": "bot",
      "content": "歡迎使用！我是您的 AI 助手，有什麼我可以幫您的嗎？",
      "created_at": 1711000000
    },
    ...
  ]
  ```

* **saved\_searches\:abc123**

  ```json
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
      "created_at": 1711000000
    },
    ...
  ]
  ```

---

## 3. RESTful API 定義

以下列出後端提供給前端使用的 API 端點、參數與範例：

### 3.1. Session 管理

| Method | Endpoint       | Query                   | 描述                                                        |
| ------ | -------------- | ----------------------- | --------------------------------------------------------- |
| GET    | `/api/session` | `session_id` (optional) | 取得或創建 Session: 如果帶 `session_id`，則嘗試取已有；否則分配新 `session_id` |
| DELETE | `/api/session` | `session_id` (required) | 刪除 Session 及其所有相關資料                                       |

### 3.2. Message 操作

| Method | Endpoint           | Query                                                          | Body                 | 描述                       |                |
| ------ | ------------------ | -------------------------------------------------------------- | -------------------- | ------------------------ | -------------- |
| POST   | `/api/message`     | `session_id` (required), `search_id` (req)                     | \`{ "role": "user    | bot", "content": str }\` | 新增訊息，回傳新增之訊息物件 |
| GET    | `/api/message`     | `session_id` (required), `search_id` (req), `limit` (optional) | `-`                  | 取得該 `search_id` 的訊息列表    |                |
| PATCH  | `/api/message`     | `session_id` (required), `search_id` (req), `message_id` (req) | `{ "content": str }` | 更新指定訊息內容，回傳更新後物件         |                |
| DELETE | `/api/message`     | `session_id` (required), `search_id` (req), `message_id` (req) | `-`                  | 刪除指定訊息                   |                |
| GET    | `/api/message/llm` | `session_id` (required), `search_id` (req), `limit` (optional) | `-`                  | 取得最新 LLM 回應訊息            |                |

### 3.3. Saved Search 操作

| Method | Endpoint            | Query                                      | Body (JSON)                                                                                               | 描述                            |
| ------ | ------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ----------------------------- |
| POST   | `/api/saved_search` | `session_id` (required)                    | `{ "title": str, "time": int, "source": int, "tags": [str], "query": str, "n": int, "range": [int,int] }` | 新增 Saved Search，回傳完整物件        |
| GET    | `/api/saved_search` | `session_id` (required)                    | `-`                                                                                                       | 取得該 Session 的 Saved Search 清單 |
| PATCH  | `/api/saved_search` | `session_id` (required), `search_id` (req) | `{ "title": str, "time": int, "source": int, "tags": [str], "query": str, "n": int, "range": [int,int] }` | 更新該 Saved Search，回傳更新後物件      |
| DELETE | `/api/saved_search` | `session_id` (required), `search_id` (req) | `-`                                                                                                       | 刪除該 Saved Search              |

### 3.4. Google Sheet & Redis 取用 (全局)

| Method | Endpoint                    | 描述                  |
| ------ | --------------------------- | ------------------- |
| GET    | `/api/sheet/kol-list`       | 取得所有 KOL 列表         |
| GET    | `/api/sheet/saved-searches` | 取得全局 Saved Searches |
| GET    | `/api/redis/kol-info`       | 取得全局 KOL Info 資料    |
| GET    | `/api/redis/kol-data`       | 取得全局 KOL Data 資料    |
| GET    | `/ping`                     | 健康檢查                |

---

## 4. 前端行為說明

以下說明前端在使用此後端時的主要互動流程。後端 domain 由 `REACT_APP_API_URL` 環境變數定義，每次請求需帶上 `API_KEY`。

### 4.1. Session 管理

1. 首次開啟網頁：

   * 檢查 `sessionStorage` 是否已有 `session_id`。

     * 有 → 直接使用該 `session_id`。
     * 無 → 向後端 `GET /api/session` 取得新的 `session_id`，並存入 `sessionStorage`。
   * 設計目的：同一瀏覽器重整時，`session_id` 不會改變，可保留所有 Saved Search 及訊息。

### 4.2. Saved Search List 快取

* 開啟列表或點擊「刷新列表」時，前端呼叫 `GET /api/saved_search?session_id=...`，將結果存入 React state，以便顯示。

### 4.3. API 呼叫時機

1. **取得/產生 SessionId**

   * 頁面初始化時，如果 `sessionStorage` 無 `session_id`，呼叫 `GET /api/session`，並將回傳的 `session_id` 存入 `sessionStorage`。
2. **取得 Saved Searches**

   * SavedSearchList 元件初始化或點擊「刷新列表」時，呼叫 `GET /api/saved_search?session_id=...`，將結果存進前端 state。
3. **新增 Saved Search**

   * 使用者操作：點擊「新增 Saved Search」 → 彈出 `SearchModal`。
   * 驗證欄位後，呼叫 `POST /api/saved_search?session_id=...`，Body 包含必要欄位。新增成功後，更新前端 state，並自動關閉 Modal。
   * 同時於後端自動分配 `id`、`order` 並紀錄 `created_at`。
4. **編輯 Saved Search**

   * 點擊「編輯」，呼叫 `PATCH /api/saved_search?session_id=...&search_id=...`，更新成功後，更新 state 並關閉 Modal。
5. **刪除 Saved Search**

   * 點擊「刪除」，呼叫 `DELETE /api/saved_search?session_id=...&search_id=...`，刪除成功後，從 state 移除。
6. **清空列表**

   * 點擊「清空列表」，抓取所有非「系統」的 `search_id`，依序呼叫 `DELETE /api/saved_search?session_id=...&search_id=...`，完成後前端 state 只保留「系統」預設項目。

### 4.4. Saved Search List 排序與顯示

* **分組與排序**: 依照 `account` 分組（系統預設最前），同組內依照 `order` 排序，確保 UI 與後端資料一致。
* **操作即時更新**: 拖曳排序、刪除、編輯等操作，皆會同步更新前端 state 與 UI。
* **拖曳排序完成**: 需呼叫後端 API 更新 Redis 中該 Session 的所有 `order` 欄位。

### 4.5. SearchModal 行為

1. **新增搜索**

   * 觸發: 點擊 Sidebar 「新增搜索」按鈕 → 彈出 `SearchModal`。
   * **取消**: 點擊「取消」或 Modal 背景 → 關閉 Modal，不送出任何請求。
   * **儲存**:

     * 欄位驗證:

       * `title` 必填，若為空顯示錯誤提示。
       * 若選擇「近 N 日」，`N` 必須為 1\~30 正整數，否則顯示錯誤提示。
       * 其它時間選項不需填 `N`。
     * 自訂區間 (時間選「自訂區間」): `RangePicker` Disabled，滑鼠移上顯示 Tooltip「功能還在開發中」。
     * 來源 (`source`)：「Threads」選項 Disabled，滑鼠移上顯示 Tooltip「功能還在開發中」。
     * KOL: 下拉選單預設 `All` (並非原始 tag)，可多選/自訂輸入，使用 Chip 顯示，點叉可移除；若 Chip 全部移除，自動還原為 `All`。
     * API 呼叫: `POST /api/saved_search?session_id=...` → 同時呼叫 `POST /api/message?session_id=...&search_id=...` 新增空訊息。
     * **傳送資料**: `title`, `account: "使用者"`, `order: 99` (由後端決定), `query` (包含所有搜尋條件)。後端自動分配 `id`, `order`, `created_at`。
     * **更新前端 State**: 新增成功後自動更新本地 state，並立即反映於 UI。
     * **關閉 Modal**: 儲存成功後自動關閉。

2. **編輯搜索**

   * 觸發: 點擊「編輯」按鈕 → 彈出 `SearchModal`。
   * 初始值: 帶入當前搜尋條件到欄位。
   * **儲存**:

     * 驗證規則與新增相同。
     * 呼叫 `PATCH /api/saved_search?session_id=...&search_id=...` 更新。
     * 僅更新 `title` 與 `query`，不更新 `id`, `account`, `order`。
     * 成功後更新前端 state，並自動關閉。

3. **檢視 (View)**

   * 觸發: 點擊「檢視」或右鍵選單「檢視」 → 彈出 `SearchModal`。
   * 初始值: 帶入當前狀態值。
   * **UI**: 所有欄位 Disabled，不可編輯；無「儲存」按鈕，僅能「關閉」；不會觸發任何 API 請求。

4. **KOL 下拉選單 (TagSelector)**

   * 元件: MUI Autocomplete + Chip。
   * 預設: `value = ["All"]`。
   * 行為: 可多選/自訂輸入，Chip 顯示且可移除；當 Chip 全部移除，自動還原 `All`。
   * Disabled 時: 無法互動。

5. **來源 (source) 中 Threads 選項**

   * **UI**: 按鈕 Disabled，滑鼠移上顯示 Tooltip「功能還在開發中」。
   * **行為**: 無法選取。

6. **補充**

   * `id` 與 `order`: `id` 為全域唯一遞增 (由後端分配)；`order` 為同一 `account` 內遞增 (由後端分配)。
   * State 與快取: 所有操作 (新增、編輯、刪除、排序) 都會同步更新本地 state 與快取，確保 UI 即時更新。
   * **API 錯誤處理**: 失敗時會在 console 顯示錯誤訊息，並以紅字提示用戶；不會讓 UI 卡死。

---

## 5. ChatPage 行為說明

ChatPage 是主要的對話頁面，開啟時會顯示歡迎訊息；若已有會話紀錄，則顯示對話內容。

* **歡迎訊息** (第一次進入):

  ```
  歡迎使用 AI 雷達站！
  您可以透過以下方式開始使用：
  1. 從左側選擇已保存的搜索條件
  2. 獲取篩選過的 KOL 數據
  3. 與 AI 助手互動分析數據
  ```

  * 如果 `GET /api/message?search_id=999` 無資料，則顯示上述歡迎訊息。

* **顯示對話**:

  * 右側顯示使用者訊息 (User)，左側顯示機器人回應 (Bot)，兩側對話框保留左右 10% padding，不貼邊。
  * 使用者訊息若寬度超過 ChatPage 2/3，會自動換行；Bot 訊息無此限制。

* **訊息傳送流程**:

  1. 使用者在輸入框輸入內容並送出 → 呼叫 `POST /api/message?session_id=...&search_id=...`。
  2. 如果成功:

     * 顯示使用者訊息在聊天框中 (即時插入)，同時存入本地快取。
     * 如果是第一次從歡迎頁面切換，入口歡迎訊息消失，變為對話紀錄介面。
     * 請求完成後，再呼叫 `POST /api/message/llm?session_id=...&search_id=...` 以取得 Bot 回應。
     * Bot 回應顯示於使用者訊息下方，並同時存入快取。
  3. 如果失敗:

     * 顯示紅色錯誤提示「訊息發送失敗，請重新發送或聯絡開發人員」。

---

## 6. Streamlit Component 使用範例

以下範例示範如何在 Streamlit App 中引用 `st_llm_search_engine`：

```python
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

# 隱藏 Streamlit 預設 UI 元素
hide_st_style = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        width: 100vw !important;
        height: 100vh !important;
    }
    .stApp {
        margin: 0 !important;
        padding: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
    }
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

# 設定後端 API URL 與金鑰
api_url = st.secrets["BACKEND_API_URL"]
api_key = st.secrets["BACKEND_API_KEY"]

# 渲染 LLM Search Component
st_llm.render(
    api_url=api_url,
    api_key=api_key
)
```

以上為完整的 `README.md` 組織與內容架構，可直接複製、貼到檔案中作為專案說明。
