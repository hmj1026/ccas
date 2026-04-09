## Context

CCAS 管線架構已支援多銀行擴充，但現有 ingest 階段僅處理 Gmail 附件下載。台北富邦銀行（FUBON, FSC code 012）有兩種帳單郵件格式：有附件（標準流程）與無附件（需 web 表單下載）。這是 CCAS 首次需要支援非附件來源的 PDF 取得方式。

使用者提供的富邦帳單郵件資訊：
- 寄件者：`rs@cf.taipeifubon.com.tw`
- 主旨格式：`台北富邦銀行YYYY年M月信用卡帳單`
- PDF 密碼規則：身分證字號
- Web 表單：點選「下載帳單明細」→ 頁面跳轉 → 輸入身分證字號 + 民國生日 + 驗證碼 → 點擊「帳單下載」

## Goals / Non-Goals

**Goals:**
- 富邦帳單（Format A 含附件）可透過現有管線自動處理
- 富邦帳單（Format B 無附件）可透過新增 web-fetch 能力自動下載 PDF
- 建立通用 BankFetcher 框架，未來其他銀行可復用
- CAPTCHA 驗證碼以 OCR 自動解析，支援重試機制
- 五階段管線架構不變（ingest → decrypt → parse → classify → notify）

**Non-Goals:**
- 不新增管線階段（web-fetch 是 ingest 階段的子步驟）
- 不實作 Playwright 瀏覽器自動化（先以 httpx 嘗試，若需 JS 再升級）
- 不支援 reCAPTCHA 或進階驗證碼（僅支援簡單圖片驗證碼）
- 不修改現有銀行的行為（BankFetcher 是 opt-in，無 fetcher 的銀行不受影響）

## Decisions

### D1: 架構選擇 — 擴充 ingest 而非新增管線階段

**選擇**: Web-fetch 作為 ingest 階段的子步驟，不新增第 6 階段。

**理由**: 管線五階段是基礎架構，新增階段影響 orchestrator、CLI、API、frontend、文件。Web-fetch 的產出與附件下載完全相同（StagedAttachment + PDF 檔案），概念上就是 ingestion 的一部分。

### D2: BankFetcher 抽象介面

**選擇**: 建立 `BankFetcher` ABC + `FetcherRegistry`，對應現有 `BankParser` / `ParserRegistry` 模式。

```
backend/src/ccas/ingestor/fetcher/
  base.py       # BankFetcher ABC, FetchError
  registry.py   # FetcherRegistry singleton
  captcha.py    # CAPTCHA OCR utility
  banks/
    fubon.py    # FubonFetcher
```

**理由**: 開發者已熟悉 Parser/Registry 模式，降低認知負擔。未來銀行只需實作 `BankFetcher` 並註冊即可。

### D3: HTTP Client 選擇

**選擇**: 先以 `httpx` + `beautifulsoup4` 實作，BankFetcher 抽象隔離實作細節。

**理由**: httpx 已在 dev dependencies 中，移至 production 無額外成本。若表單需要 JavaScript，可在 FubonFetcher 內部替換為 Playwright 而不影響介面。Playwright 會增加 Docker image ~300MB。

### D4: CAPTCHA OCR 策略

**選擇**: 使用已安裝的 pytesseract（`--psm 7` 單行模式 + 字元白名單），搭配重試機制（最多 3 次）。

**理由**: pytesseract + tesseract-ocr 已在 Docker 中安裝，無新增依賴。簡單英數驗證碼單次辨識率約 60-80%，3 次重試後成功率約 90-95%。失敗時記錄 log 供人工檢視。

### D5: GmailMessage 擴充

**選擇**: 新增 `html_body: str | None = None` 欄位，僅在郵件無 PDF 附件時填充。

**理由**: 非破壞性變更（新增 optional field with default）。現有程式碼只讀取 `pdf_attachments`，不受影響。避免對所有郵件提取 HTML body 的效能開銷。

### D6: StagedAttachment 來源追蹤

**選擇**: 新增 `source_type` 欄位（`"attachment"` | `"web_fetch"`），`server_default="attachment"`。

**理由**: Alembic migration 向後相容，既有資料自動補 default。Web-fetch 的 `gmail_attachment_id` 使用合成值 `"web_fetch_{message_id}"`，保持既有 unique constraint 不變。

### D7: 憑證管理

**選擇**: 新增 `FUBON_NATIONAL_ID`、`FUBON_ROC_BIRTHDAY` 環境變數，擴充 `Settings` 新增 `get_bank_credential(bank_code, key)` 方法。

**理由**: 遵循 `PDF_PASSWORD_{BANK_CODE}` 的命名模式。民國生日格式固定為 7 碼（如 0881010），在文件中說明。

### D8: Parser 辨識策略

**選擇**: 使用 PDF 首頁文字特徵辨識（關鍵字 `"台北富邦"` + `"信用卡"`）。

**理由**: 與 CTBC 一致的模式。

### D9: 檔案結構

```
backend/src/ccas/parser/banks/fubon_v1.py      # parser 實作
backend/tests/unit/parser/test_fubon_v1.py      # 單元測試
backend/tests/fixtures/fubon/                   # 測試用合成 PDF
```

## Risks / Trade-offs

- **[CAPTCHA OCR 不可靠]** → 單次辨識率約 60-80%。**Mitigation**: 重試機制（3 次）；log 失敗驗證碼圖片；未來可接入專業驗證碼辨識服務。
- **[Web 表單需要 JavaScript]** → httpx 無法處理 JS 渲染頁面。**Mitigation**: BankFetcher 抽象隔離；若確認需 JS，FubonFetcher 內部替換為 Playwright，介面不變。
- **[銀行改版表單]** → URL 或表單欄位可能變動。**Mitigation**: URL 從郵件 HTML 動態提取（不硬編碼）；表單 selector 變更時實作 v2 fetcher。
- **[PDF 格式未知]** → 尚無實際富邦帳單 PDF 樣本。**Mitigation**: v1 parser 先以合理假設實作骨架，取得真實帳單後快速迭代。
- **[search_messages 行為變更]** → 不再過濾無附件郵件。**Mitigation**: 非破壞性 — `html_body` 是新增欄位；現有程式碼只讀 `pdf_attachments`。
