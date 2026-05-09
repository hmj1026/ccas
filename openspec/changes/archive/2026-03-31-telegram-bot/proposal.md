## 緣由 (Why)

CCAS 的主要使用介面之一是 Telegram Bot。使用者需要在帳單解析完成後收到主動通知，也要能透過 Telegram 直接查詢本月待繳、已繳、即將到期與指定月份摘要，因此需要一個獨立的 bot change 來定義命令行為、通知內容與帳單狀態操作。

## 變更內容 (What Changes)

- 新增 Telegram Bot 指令處理，支援 `/status`、`/upcoming`、`/paid`、`/summary`、`/category`
- 新增主動通知能力，涵蓋新帳單解析完成、繳費提醒與解析失敗通知
- 新增 Telegram 端標記帳單已繳的流程
- 新增查詢結果與通知訊息的文字格式規格

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `telegram-command-handlers`: 定義查詢指令與回覆內容
- `telegram-bill-actions`: 定義 `/paid` 指令對帳單狀態的影響
- `telegram-notifications`: 定義主動推播事件與訊息摘要格式

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: `bot/`、`storage/`
- **資料讀寫**: 查詢 `bills`、`transactions`，更新 `Bill.is_paid`
- **使用者互動**: 建立第一個可直接給最終使用者使用的查詢與通知介面
