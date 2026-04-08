## Phase 1: Bootstrap 設定

- [ ] 1.1 在 `config/banks.example.yaml` 新增 FUBON 銀行設定（gmail_filter: `from:rs@cf.taipeifubon.com.tw subject:台北富邦銀行 subject:信用卡帳單`、active_parser_version: v1、is_active: true）
- [ ] 1.2 在 `.env.example` 新增 `PDF_PASSWORD_FUBON` 環境變數註解與說明（密碼規則：身分證字號）
- [ ] 1.3 在 `.env.example` 新增 `FUBON_NATIONAL_ID`、`FUBON_ROC_BIRTHDAY` 環境變數註解與說明（民國生日格式：7 碼，如 0881010）
- [ ] 1.4 在 `config/bank-code-registry.yaml` 將 FUBON 的 `supported` 改為 `true`，更新 notes

## Phase 2: Fetcher 框架

- [ ] 2.1 建立 `backend/src/ccas/ingestor/fetcher/base.py`，定義 `BankFetcher` 抽象介面與 `FetchError`
- [ ] 2.2 建立 `backend/src/ccas/ingestor/fetcher/registry.py`，實作 `FetcherRegistry` 單例
- [ ] 2.3 擴充 `GmailMessage` dataclass 新增 `html_body: str | None = None` 欄位
- [ ] 2.4 修改 `search_messages()` — 無附件郵件不再過濾，改為填充 `html_body` 回傳
- [ ] 2.5 在 `StagedAttachment` model 新增 `source_type` 欄位（server_default="attachment"）
- [ ] 2.6 建立 Alembic migration：`alembic revision --autogenerate -m "add-staged-attachment-source-type"`
- [ ] 2.7 擴充 `Settings` 新增 `get_bank_credential(bank_code, key)` 方法
- [ ] 2.8 修改 `run_ingestion_job()` — 新增 web-fetch 程式碼路徑（檢查 FetcherRegistry、呼叫 `_process_web_fetch()`）
- [ ] 2.9 實作 `_process_web_fetch()` — 呼叫 fetcher、存檔 PDF、建立 StagedAttachment（source_type="web_fetch"、合成 gmail_attachment_id）
- [ ] 2.10 撰寫 fetcher 框架單元測試（BankFetcher 子類化、FetcherRegistry 註冊/查找、GmailMessage html_body）

## Phase 3: Fubon Fetcher 實作

- [ ] 3.1 建立 `backend/src/ccas/ingestor/fetcher/captcha.py`，實作 `solve_captcha(image_bytes) -> str`（pytesseract --psm 7 + 英數白名單）
- [ ] 3.2 建立 `backend/src/ccas/ingestor/fetcher/banks/fubon.py`，實作 `FubonFetcher`
- [ ] 3.3 實作 `can_fetch()` — 使用 BeautifulSoup 偵測「下載帳單明細」連結
- [ ] 3.4 實作 `fetch_pdf()` — URL 提取 → 頁面訪問 → CAPTCHA OCR → 表單提交 → PDF 下載（httpx）
- [ ] 3.5 實作 CAPTCHA 重試機制（最多 3 次，每次重新取得 CAPTCHA）
- [ ] 3.6 模組層級呼叫 `fetcher_registry.register(FubonFetcher())`
- [ ] 3.7 新增 `httpx`（production dependency）與 `beautifulsoup4` 至 `backend/pyproject.toml`

## Phase 4: Fetcher 測試

- [ ] 4.1 撰寫 `backend/tests/unit/ingestor/test_captcha.py`（OCR 辨識、失敗處理、tesseract 不可用）
- [ ] 4.2 撰寫 `backend/tests/unit/ingestor/test_fubon_fetcher.py`（can_fetch 正反例、URL 提取、表單填寫邏輯，mock httpx）
- [ ] 4.3 撰寫 `backend/tests/integration/ingestor/test_web_fetch_job.py`（使用 mock fetcher 測試 _process_web_fetch 完整流程、StagedAttachment 建立、source_type 正確）
- [ ] 4.4 執行完整測試套件確認無回歸

## Phase 5: Parser 實作

- [ ] 5.1 建立 `backend/src/ccas/parser/banks/fubon_v1.py`，實作 `FubonV1Parser` 類別（繼承 `BankParser`，bank_code="FUBON"，version="v1"）
- [ ] 5.2 實作 `can_parse()` — 以首頁文字特徵「台北富邦」+「信用卡」辨識
- [ ] 5.3 實作 `_extract_summary()` — 提取 billing_month、total_amount、due_date
- [ ] 5.4 實作 `_extract_transactions()` — 提取交易明細（trans_date、merchant、amount、posting_date、card_last4）
- [ ] 5.5 模組層級呼叫 `registry.register(FubonV1Parser())`
- [ ] 5.6 更新 `backend/src/ccas/parser/banks/__init__.py` 加入 `from . import fubon_v1`

## Phase 6: Parser 單元測試

- [ ] 6.1 在 `backend/tests/unit/parser/conftest.py` 新增 FUBON 文字 fixture 常數（首頁文字、交易行、預期摘要值）
- [ ] 6.2 撰寫 `backend/tests/unit/parser/test_fubon_v1.py`（can_parse 正反例、摘要提取、交易提取、錯誤處理）
- [ ] 6.3 執行 `./scripts/dev-test.sh tests/unit/parser/test_fubon_v1.py -v` 確認全部通過

## Phase 7: Parser 整合測試

- [ ] 7.1 撰寫 `backend/tests/integration/parser/test_fubon_v1_pdf.py`，以 fpdf2 產生合成富邦帳單 PDF（參照 `test_ctbc_v1_pdf.py`）
- [ ] 7.2 測試案例：can_parse 正確辨識、非富邦 PDF 拒絕、parse 回傳完整 ParseResult、多頁帳單、結果不可變性
- [ ] 7.3 測試 registry 整合：import `ccas.parser.banks` 後 FUBON parser 已自動註冊

## Phase 8: 整合測試 — Parse Job & API

- [ ] 8.1 撰寫 `backend/tests/integration/parser/test_fubon_parse_job.py`（合成 PDF + FubonV1Parser → Bill/Transaction DB 紀錄）
- [ ] 8.2 驗證 `GET /api/bills?bank_code=FUBON` 與 `GET /api/transactions?bank_code=FUBON` 回應正確

## Phase 9: 文件更新

- [ ] 9.1 更新 `docs/user-guide.md` 新增富邦銀行設定說明（Gmail filter、PDF 密碼規則、web-fetch 憑證設定、兩種郵件格式說明）
