## Context

`setup.sh` 目前使用 `require_env` 對 `TELEGRAM_CHAT_ID` 和 `TELEGRAM_ALLOWED_CHAT_IDS` 做強制驗證：未設定就立即 fail。但 Telegram chat_id 有個雞生蛋的問題：用戶必須先對 bot 傳訊息並呼叫 `getUpdates` API 才能取得自己的 chat_id，而在這之前他們可能需要先跑 pipeline 確認整體設定是否正常。

目前 `notify` 職位的實作已有安全的早退邏輯：若無帳單就直接回傳不發訊息。問題在於 setup.sh 的驗證比 pipeline 本身更嚴格，把不是 blocker 的設定誤當成 blocker。

## Goals / Non-Goals

**Goals:**
- setup.sh 對 `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_CHAT_IDS` 由 hard fail 改為 warn
- 警告訊息明確說明：影響範圍僅限 notify stage
- `Settings.telegram_chat_id` 加上 `= ""` 預設值，避免 ValidationError（`telegram_allowed_chat_ids` 已有預設值）

**Non-Goals:**
- 不改變 notify job 的行為（chat_id 為空時送訊息會失敗，但這是 runtime 問題）
- 不移除 `TELEGRAM_BOT_TOKEN` 的必填驗證

## Decisions

**D1 — 用 `warn_env` 替代 `require_env`**

在 `setup.sh` 裡加一個 `warn_env()` helper，列印黃色 `[WARN]` 訊息但不 `exit 1`。把 `TELEGRAM_CHAT_ID` 和 `TELEGRAM_ALLOWED_CHAT_IDS` 的 `require_env` 改為 `warn_env`。

_替代方案考量：_ 把整個 Telegram 區塊移到設定最後、執行完 bank sync 後再驗證 — 雖然可行，但仍會 block，只是時序不同，不解決根本問題。

**D2 — `Settings.telegram_chat_id` 加預設值 `""`**

目前 `telegram_chat_id: str`（無預設），若環境變數完全缺失（非空字串）會觸發 pydantic ValidationError，而非優雅降級。加上 `= ""` 與既有的 `telegram_allowed_chat_ids: str = ""` 一致。

## Risks / Trade-offs

- [Risk] 用戶設定不完整就跑 pipeline，notify 階段會因 chat_id 空而失敗 → Mitigation: notify job 已有 `if not bills: return`；若有帳單且 chat_id 空，pipeline 會在 failures 中記錄錯誤，不會靜默失敗
- [Risk] 移除強制驗證後，用戶可能忘記設定 Telegram → Mitigation: warn 訊息明確提示，且 `TELEGRAM_BOT_TOKEN` 仍是必填

## Migration Plan

1. 修改 `scripts/setup.sh`：加 `warn_env()` helper，替換 TELEGRAM_CHAT_ID/ALLOWED 的 `require_env`
2. 修改 `backend/src/ccas/config.py`：`telegram_chat_id: str = ""`
3. 無資料 migration，無 API 變更
