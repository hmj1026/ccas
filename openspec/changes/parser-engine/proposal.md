## 緣由 (Why)

`gmail-ingestor` 只負責把帳單 PDF 抓回本地 staging 區，但系統還缺少能將不同銀行 PDF 解析成結構化帳單與交易資料的核心引擎。由於各家銀行格式不同且會隨時間變動，需要一個可版本化、可回退、可追蹤失敗原因的 parser engine。

## 變更內容 (What Changes)

- 新增可依銀行與版本管理 parser 的 registry
- 新增統一的 bank parser 介面與 `ParseResult` 資料契約
- 新增從 staged PDF 執行解析、寫入 `bills` 與 `transactions` 的流程
- 新增解析失敗處理，將附件標記為 `parse_failed` 並保留錯誤原因
- 新增人工審查待處理佇列的資料語意，以便後續介面與通知串接

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `parser-registry`: 依銀行代碼與版本註冊、發現與選擇 parser
- `bank-parser-contract`: 定義 `can_parse()`、`parse()` 與 `ParseResult` 的標準契約
- `parse-orchestration`: 從 staged attachment 執行解析、持久化帳單與交易、更新解析狀態

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: `parser/`、`storage/`
- **資料模型語意**: `bills`、`transactions` 寫入流程，以及 staged attachment 的 `parse_failed` / `parsed` 狀態轉換
- **作業流程**: 讓 Gmail 附件可被轉成結構化資料，供 classifier、Telegram 與 dashboard 使用
