## 1. Bootstrap 設定

- [ ] 1.1 在 `config/banks.example.yaml` 新增 UBOT 銀行設定（gmail_filter: `from:estatement@ebillv2.card.ubot.com.tw subject:聯邦銀行信用卡 subject:電子帳單`、active_parser_version: v1、is_active: true）
- [ ] 1.2 在 `.env.example` 新增 `PDF_PASSWORD_UBOT` 環境變數註解與說明
- [ ] 1.3 在 `config/bank-code-registry.yaml` 將 UBOT 的 `supported` 改為 `true`，更新 notes

## 2. Parser 實作

- [ ] 2.1 建立 `backend/src/ccas/parser/banks/ubot_v1.py`，實作 `UbotV1Parser` 類別（繼承 `BankParser`，bank_code="UBOT"，version="v1"）
- [ ] 2.2 實作 `can_parse()` -- 以首頁文字特徵「聯邦銀行」+「信用卡」辨識
- [ ] 2.3 實作 `_extract_summary()` -- 提取 billing_month、total_amount、due_date
- [ ] 2.4 實作 `_extract_transactions()` -- 提取交易明細（trans_date、merchant、amount、posting_date、card_last4）
- [ ] 2.5 模組層級呼叫 `registry.register(UbotV1Parser())`
- [ ] 2.6 在 `backend/src/ccas/parser/banks/__init__.py` 新增 `from . import ubot_v1`

## 3. 單元測試

- [ ] 3.1 在 `backend/tests/unit/parser/conftest.py` 新增 UBOT 文字 fixture 常數（首頁文字、交易行、預期摘要值）
- [ ] 3.2 撰寫 `backend/tests/unit/parser/test_ubot_v1.py`（can_parse 正反例、摘要提取、交易提取、錯誤處理）
- [ ] 3.3 執行 `./scripts/dev-test.sh tests/unit/parser/test_ubot_v1.py -v` 確認全部通過

## 4. 整合測試 -- 合成 PDF 解析

- [ ] 4.1 撰寫 `backend/tests/integration/parser/test_ubot_v1_pdf.py`，以 fpdf2 產生合成聯邦帳單 PDF（參照 `test_ctbc_v1_pdf.py`）
- [ ] 4.2 測試案例：can_parse 正確辨識、非聯邦 PDF 拒絕、parse 回傳完整 ParseResult、多頁帳單、結果不可變性
- [ ] 4.3 測試 registry 整合：import `ccas.parser.banks` 後 UBOT parser 已自動註冊

## 5. 整合測試 -- Parse Job 寫入 DB

- [ ] 5.1 撰寫 `backend/tests/integration/parser/test_ubot_parse_job.py`，使用真實 UbotV1Parser + 合成 PDF 呼叫 `run_parse_job()`（參照 `test_job.py`）
- [ ] 5.2 驗證 Bill 紀錄：bank_code="UBOT"、billing_month、total_amount、due_date 正確
- [ ] 5.3 驗證 Transaction 紀錄：筆數、merchant、amount 正確
- [ ] 5.4 驗證 StagedAttachment.status 轉為 "parsed"

## 6. 整合測試 -- API 回應

- [ ] 6.1 seed UBOT BankConfig + Bill + Transaction，驗證 `GET /api/bills?bank_code=UBOT` 回應正確（可擴充 `test_bills.py` 或獨立檔案）
- [ ] 6.2 驗證 `GET /api/transactions?bank_code=UBOT` 回應包含 UBOT 交易明細

## 7. 文件更新

- [ ] 7.1 更新 `docs/user-guide.md` 新增聯邦銀行設定說明（Gmail filter、PDF 密碼、banks.yaml 設定）
