## Context

`Settings` 使用 pydantic-settings `BaseSettings`，設定 `env_file="../.env"`。pydantic-settings 會將 `.env` 值載入 model 欄位，但不會寫入 `os.environ`。兩個函式繞過 pydantic-settings 直接呼叫 `os.environ.get()`：

1. `Settings.get_pdf_password()` — 動態鍵 `PDF_PASSWORD_{BANK_CODE}`
2. `bot/auth.py:load_allowed_chat_ids()` — 靜態鍵 `TELEGRAM_ALLOWED_CHAT_IDS`

當這些值僅存在於 `.env`（未 shell export）時，兩個函式都會靜默回傳空值/None。

## Goals / Non-Goals

**目標：**
- `get_pdf_password()` 同時從 `.env` 檔和真實環境變數讀取
- `TELEGRAM_ALLOWED_CHAT_IDS` 作為正式 Settings 欄位管理
- 真實環境變數優先於 `.env` 檔中的值
- 不破壞現有 mock 測試邊界（`settings.get_pdf_password`）

**非目標：**
- 重構其他設定模式（如 `get_frontend_origins`）
- 新增銀行代碼或密碼管理功能
- 變更 `.env` 檔路徑或載入策略

## Decisions

### D1：使用 `PrivateAttr` env map 處理動態鍵

`PDF_PASSWORD_CTBC` 等動態鍵無法作為獨立的 Settings 欄位，因為銀行代碼由使用者定義。改在 `Settings` 初始化時透過 `dotenv_values()` 解析 `.env`，與 `os.environ` 合併為私有的 `_env_map` 字典。`get_pdf_password()` 從此 map 讀取。

**曾考慮方案**：啟動時呼叫 `load_dotenv()` 全域填充 `os.environ`。因會產生隱藏的全域副作用且重複解析 `.env`（pydantic-settings 已解析過）而放棄。

**曾考慮方案**：每次呼叫 `get_pdf_password()` 時執行 `dotenv_values()`。因每次呼叫都重新讀取檔案且無快取而放棄。

### D2：將 `telegram_allowed_chat_ids` 加為 Settings 欄位

這是一個靜態、已知的鍵。正確的 pydantic-settings 模式是帶預設值的 model 欄位。重構 `load_allowed_chat_ids()` 改為接受原始字串參數，而非直接讀取 `os.environ`。

**曾考慮方案**：保留在 `os.environ` 中透過 `load_dotenv()` 修正。依 D1 理由放棄——應遵循既有的 Settings 模式。

### D3：使用 `model_post_init` 初始化 env map

pydantic v2 的 `model_post_init` 是文件記載的後初始化 hook。由於 BaseSettings model 預設為 frozen，使用 `object.__setattr__` 設定 `PrivateAttr` 值。

## Risks / Trade-offs

- [風險] `dotenv_values()` 會第二次讀取 `.env`（pydantic-settings 已讀取過一次）→ 可接受：僅在啟動時發生一次，檔案很小，且我們需要 pydantic-settings 未公開的原始鍵值對。
- [風險] `_env_map` 是初始化時的快照；後續環境變數變更不會反映 → 可接受：`Settings` 已經是 `lru_cache` 單例；執行時期環境變數變更不是支援的模式。
- [風險] `PrivateAttr` + `model_post_init` 與 pydantic-settings v2 的相容性 → 已緩解：兩者都是標準 pydantic v2 功能，廣泛搭配使用。
