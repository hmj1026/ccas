## 1. Settings 類別變更

- [x] 1.1 在 `config.py` 的 `Settings` 中新增 `telegram_allowed_chat_ids: str = ""` 欄位
- [x] 1.2 在 `Settings` 中新增 `_env_map: dict[str, str]` 作為 `PrivateAttr`
- [x] 1.3 新增 `model_post_init`，從 `dotenv_values()` 與 `os.environ` 合併建立 `_env_map`
- [x] 1.4 更新 `get_pdf_password()` 改從 `self._env_map` 讀取，取代 `os.environ`

## 2. Bot 認證重構

- [x] 2.1 變更 `load_allowed_chat_ids()` 簽章，改為接受 `raw: str` 參數
- [x] 2.2 移除 `bot/auth.py` 中的 `os` import
- [x] 2.3 更新 `bot/app.py` 的 `create_bot_app()`，傳入 `settings.telegram_allowed_chat_ids`

## 3. 測試更新

- [x] 3.1 更新 `test_auth.py`，改為直接傳入字串而非 `monkeypatch.setenv`
- [x] 3.2 執行現有 `test_password.py` 與 `test_job.py` 確認無破壞

## 4. 驗證

- [x] 4.1 執行 `uv run ruff check .` 與 `uv run pyright` — 無新錯誤
- [x] 4.2 執行 `uv run pytest tests/unit/ tests/integration/` — 全部通過

## 5. 修正 `_env_file` 執行階段覆寫未反映至 `_env_map`

- [x] 5.1 將 `_env_map` 建構邏輯提取為 `_build_env_map()` helper
- [x] 5.2 覆寫 `__init__`：擷取 `_env_file` kwarg，`super()` 後若有覆寫則重建 `_env_map`
- [x] 5.3 新增 `tests/unit/test_config.py`：自訂 env file、`_env_file=None`、`os.environ` 優先等 5 個測試
- [x] 5.4 驗證：pyright 0 errors、pytest 418 passed
