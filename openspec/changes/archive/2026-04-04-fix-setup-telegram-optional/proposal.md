## Why

`setup.sh` 在執行 Gmail OAuth 和 bank sync 之前就強制要求 `TELEGRAM_CHAT_ID` 與 `TELEGRAM_ALLOWED_CHAT_IDS`，但這兩個值只有在 notify stage 才會用到。這導致新用戶在尚未取得 Telegram chat_id 的情況下，連基本的 ingest/decrypt/parse/classify 都無法跑通，形成不必要的設定障礙。

## What Changes

- `setup.sh` 的 `TELEGRAM_CHAT_ID` 與 `TELEGRAM_ALLOWED_CHAT_IDS` 驗證改為警告（warning）而非失敗（error）
- 警告訊息需明確說明：缺少這兩個值只會影響 notify stage，其他 stage 不受影響
- 保留 `TELEGRAM_BOT_TOKEN` 的必填驗證（bot token 設定相對簡單，且 notify stage 需要）
- `Settings` 中 `telegram_chat_id: str` 無預設值 → 加入空字串預設值（可選）

## Capabilities

### New Capabilities
<!-- 無新 capability，此為 setup 流程調整 -->

### Modified Capabilities
- `local-dev-startup`: setup.sh 的 Telegram 驗證邏輯改變

## Impact

- `scripts/setup.sh` — 移除 `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_CHAT_IDS` 的 `require_env` 強制檢查，改為警告輸出
- `backend/src/ccas/config.py` — `telegram_chat_id: str` 可考慮加上 `= ""` 預設值（避免 Settings 在 TELEGRAM_CHAT_ID 完全未設定時 ValidationError）
- 不影響 pipeline 執行流程，notify job 已有 `if not bills: return` 的早退邏輯
