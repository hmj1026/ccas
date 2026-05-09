## 1. scripts/setup.sh — 降級 Telegram 驗證

- [x] 1.1 在 `setup.sh` 加入 `warn_env()` helper 函數：印出 `[WARN]` 訊息但不 exit
- [x] 1.2 把 `require_env "TELEGRAM_CHAT_ID" ...` 改為 `warn_env "TELEGRAM_CHAT_ID" "notify stage 將無法發送 Telegram 通知，其他 stage 不受影響"`
- [x] 1.3 把 `require_env "TELEGRAM_ALLOWED_CHAT_IDS" ...` 改為 `warn_env "TELEGRAM_ALLOWED_CHAT_IDS" "Telegram Bot 命令功能將受限"`

## 2. backend/src/ccas/config.py — 加入預設值

- [x] 2.1 將 `telegram_chat_id: str` 改為 `telegram_chat_id: str = ""`

## 3. 驗證

- [x] 3.1 以空的 `TELEGRAM_CHAT_ID` 執行 `scripts/setup.sh`，確認不再 fail，出現 `[WARN]` 訊息
- [x] 3.2 執行 `uv run python -m ccas.pipeline --bank CTBC`，確認 pipeline 正常跑完
- [x] 3.3 執行 `uv run python -c "from ccas.config import Settings; s = Settings(); print(s.telegram_chat_id)"` 確認空字串預設值
