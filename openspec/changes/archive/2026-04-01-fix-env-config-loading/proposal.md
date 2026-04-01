## Why

`Settings`（pydantic-settings）透過 `env_file="../.env"` 載入設定，但有兩個函式繞過 pydantic-settings 直接呼叫 `os.environ.get()`。pydantic-settings 不會將 `.env` 的值寫入 `os.environ`——只在 `.env` 中定義（未在 shell export）的變數對這些函式不可見。這導致 `get_pdf_password()` 回傳 `None`、`load_allowed_chat_ids()` 回傳空值，即使 `.env` 檔中已有正確設定。

## What Changes

- 修正 `Settings.get_pdf_password()`，使其能從 `.env` 檔讀取動態 `PDF_PASSWORD_{BANK_CODE}` 鍵值（不僅限 `os.environ`）
- 將 `telegram_allowed_chat_ids` 加為正式的 `Settings` 欄位，讓 pydantic-settings 原生從 `.env` 載入
- 重構 `load_allowed_chat_ids()` 改為接受 Settings 提供的原始字串參數，不再直接讀取 `os.environ`
- 更新測試以反映新的參數式簽章

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `app-config`：`Settings` 新增 `_env_map` 私有屬性用於動態環境變數鍵查詢，以及新欄位 `telegram_allowed_chat_ids`
- `telegram-command-handlers`：`load_allowed_chat_ids()` 簽章從無參數改為接受原始字串參數

## Impact

- `backend/src/ccas/config.py` — Settings 類別變更（新欄位、PrivateAttr、model_post_init）
- `backend/src/ccas/bot/auth.py` — `load_allowed_chat_ids()` 簽章變更
- `backend/src/ccas/bot/app.py` — 呼叫端更新，傳入 settings 值
- `backend/tests/unit/bot/test_auth.py` — 測試更新為新簽章
- 無資料庫、API 或 migration 變更
