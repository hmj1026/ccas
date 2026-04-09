## Why

CCAS 目前已支援中國信託（CTBC），永豐（SINOPAC）、玉山（ESUN）、聯邦（UBOT）、台新（TAISHIN）、國泰世華（CATHAY）已建立 OpenSpec 變更但尚未實作。使用者持有台北富邦銀行（Taipei Fubon Bank）信用卡，需要將富邦帳單納入同一自動化管線。

台北富邦銀行已在 `bank-code-registry.yaml` 預定義（bank_code: FUBON, fsc_code: 012），但目前 `supported: false`。

**與其他銀行的關鍵差異**：富邦帳單郵件有兩種格式：
1. **Format A（含附件）**：郵件直接附帶 PDF 帳單，與其他銀行相同
2. **Format B（無附件）**：郵件僅含「下載帳單明細」連結，需至網頁表單輸入身分證字號、民國生日、驗證碼後下載 PDF

現有 ingest 階段僅處理 Gmail 附件，無附件的郵件會被靜默跳過。Format B 需要新的 web-fetch 能力。

使用者提供的富邦帳單郵件資訊：
- 寄件者：`rs@cf.taipeifubon.com.tw`
- 主旨格式：`台北富邦銀行YYYY年M月信用卡帳單`
- PDF 密碼規則：身分證字號
- Web 表單下載流程：點選「下載帳單明細」→ 填寫身分證字號 + 民國生日（如 0881010）+ 驗證碼 → 點擊「帳單下載」

## What Changes

### 標準銀行支援（與其他銀行相同）
- 新增 FUBON 銀行設定至 `banks.example.yaml`（Gmail filter、parser version、is_active）
- 新增 `PDF_PASSWORD_FUBON` 環境變數至 `.env.example`
- 在 `bank-code-registry.yaml` 將 FUBON 標記為 `supported: true`
- 實作 `FubonV1Parser`（繼承 `BankParser`，實作 `can_parse` / `parse`）
- 在 parser registry 自動註冊 FUBON parser

### 新增 Web-Fetch 框架（跨銀行共用）
- 新增 `BankFetcher` 抽象介面與 `FetcherRegistry`（對應 `BankParser` / `ParserRegistry` 模式）
- 擴充 `GmailMessage` 支援 `html_body` 欄位（僅無附件郵件填充）
- 擴充 `search_messages()` 不再過濾無附件郵件
- 擴充 `run_ingestion_job()` 新增 web-fetch 程式碼路徑
- `StagedAttachment` 新增 `source_type` 欄位（Alembic migration）

### 富邦專屬 Web-Fetch 實作
- 實作 `FubonFetcher`（從郵件 HTML 提取下載連結、填寫表單、OCR 驗證碼）
- 新增 CAPTCHA OCR 工具（基於已安裝的 pytesseract）
- 新增 `FUBON_NATIONAL_ID`、`FUBON_ROC_BIRTHDAY` 環境變數

## Capabilities

### New Capabilities
- `fubon-bootstrap`: 富邦銀行設定（Gmail filter、PDF password key、banks.yaml 設定）
- `fubon-parser`: 富邦銀行信用卡帳單 PDF parser（v1），解析帳單摘要與交易明細
- `fubon-fetcher-framework`: 通用 Web-Fetch 框架（BankFetcher ABC、FetcherRegistry、GmailMessage 擴充、ingest job web-fetch 路徑、StagedAttachment source_type）
- `fubon-fetcher-impl`: 富邦銀行專屬 fetcher 實作（URL 提取、表單填寫、驗證碼 OCR）

### Modified Capabilities
- `ingest`（隱含修改）：ingest job 需識別並處理無附件郵件的 web-fetch 路徑

## Impact

- **Config**: `banks.example.yaml`、`.env.example`、`bank-code-registry.yaml`
- **Ingestor**: 新增 `backend/src/ccas/ingestor/fetcher/` 模組，修改 `gmail_client.py`、`job.py`
- **Parser**: 新增 `backend/src/ccas/parser/banks/fubon_v1.py`，更新 `__init__.py`
- **Storage**: `StagedAttachment` 新增 `source_type` 欄位 + Alembic migration
- **Config module**: `Settings` 新增 `get_bank_credential()` 方法
- **Tests**: 新增 fetcher 框架測試、FubonFetcher 測試、parser 測試
- **Docs**: `docs/user-guide.md` 新增富邦銀行設定說明
- **依賴**: 新增 `httpx`（production）、`beautifulsoup4`（HTML 解析）；若需 JS 則後續加入 `playwright`
