## 1. Bot 基礎與認證

- [ ] 1.1 實作 chat_id 白名單驗證 middleware，從環境變數 `TELEGRAM_ALLOWED_CHAT_IDS` 讀取
- [ ] 1.2 非白名單 chat_id 的訊息靜默忽略，不回覆任何內容

## 2. Bot 指令層

- [ ] 2.1 建立 `/status`、`/upcoming`、`/summary`、`/category` 指令 handler
- [ ] 2.2 定義各指令所需的 repository 查詢與摘要格式
- [ ] 2.3 處理缺少資料、無結果與參數錯誤的回覆情境
- [ ] 2.4 `/status` 回覆中每筆帳單附上 `bill_id`，方便使用者複製用於 `/paid`
- [ ] 2.5 多銀行帳單依銀行分組顯示，每組包含銀行名稱、帳單列表與小計

## 3. 帳單操作

- [ ] 3.1 建立 `/paid {bill_id}` 指令 handler
- [ ] 3.2 實作帳單狀態更新與冪等回覆行為
- [ ] 3.3 處理無效 `bill_id` 與找不到帳單的錯誤訊息

## 4. 主動通知

- [ ] 4.1 建立新帳單解析完成通知的 rendering 與發送流程
- [ ] 4.2 建立到期前 3 天與 1 天的提醒訊息格式（排程觸發由 `pipeline-scheduler` 負責）
- [ ] 4.3 建立解析失敗通知的 rendering 與發送流程
- [ ] 4.4 實作 Telegram API 呼叫的 exponential backoff retry（最多 3 次，1s/2s/4s），針對 429 與 5xx 狀態碼

## 5. 測試覆蓋

- [ ] 5.1 新增 chat_id 白名單驗證測試（允許/拒絕/靜默忽略）
- [ ] 5.2 新增查詢指令回覆格式的單元測試（含 bill_id 顯示、多銀行分組）
- [ ] 5.3 新增 `/paid` 狀態更新與錯誤處理測試
- [ ] 5.4 新增通知摘要內容與觸發條件測試
- [ ] 5.5 新增 Telegram API retry 行為的單元測試（429/5xx 重試、非暫時性錯誤不重試）
