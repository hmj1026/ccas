## 緣由 (Why)

CCAS 的自動化流程需要先把帳單 PDF 從 Gmail 安全且可追蹤地抓回本地，後續 parser、分類、Telegram 推播與報表能力才能建立在穩定的輸入來源上。現在 `foundation-setup` 只建立了基礎架構，尚未定義真正的帳單匯入能力，因此需要先補上 Gmail ingestion change。

## 變更內容 (What Changes)

- 新增 Gmail 帳單抓取能力，使用 Gmail API 依 `bank_configs.gmail_filter` 搜尋候選郵件
- 新增 PDF 附件辨識與下載流程，將附件落地到後端管理的資料目錄
- 新增附件 staging 能力，保存每個附件對應的 Gmail message、銀行代碼、檔名、路徑、處理狀態與錯誤原因
- 新增重跑去重複邏輯，避免同一封郵件或同一個附件被重複匯入
- 定義可由 scheduler 呼叫的 ingestion job 入口，供後續排程 change 串接

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `gmail-ingestion`: 透過 Gmail API 搜尋帳單郵件、過濾 PDF 附件並下載到本地 staging 區
- `attachment-staging`: 保存下載附件的追蹤資料、檔案位置、處理狀態與失敗原因，供後續 parser 接手
- `ingestion-job-hook`: 定義單次 ingestion job 的執行邊界、輸出摘要與失敗不中止的批次處理行為

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: `ingestor/`、`storage/`、`config.py`
- **資料庫**: 新增附件 staging 資料表與對應 migration
- **外部系統**: Gmail API OAuth、Gmail message/attachment metadata
- **執行行為**: 建立可重跑、可追蹤的帳單附件匯入流程
