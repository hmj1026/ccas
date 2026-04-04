## 1. Bootstrap 設定

- [ ] 1.1 在 `config/banks.example.yaml` 新增 SINOPAC 銀行設定（gmail_filter、active_parser_version: v1、is_active: true）
- [ ] 1.2 在 `.env.example` 新增 `PDF_PASSWORD_SINOPAC` 環境變數註解與說明
- [ ] 1.3 在 `config/bank-code-registry.yaml` 將 SINOPAC 的 `supported` 改為 `true`，更新 notes

## 2. Parser 實作

- [ ] 2.1 建立 `backend/src/ccas/parser/banks/sinopac_v1.py`，實作 `SinopacV1Parser` 類別（繼承 `BankParser`，bank_code="SINOPAC"，version="v1"）
- [ ] 2.2 實作 `can_parse()` — 以首頁文字特徵「永豐銀行」+「信用卡」辨識
- [ ] 2.3 實作 `_extract_summary()` — 提取 billing_month、total_amount、due_date
- [ ] 2.4 實作 `_extract_transactions()` — 提取交易明細（trans_date、merchant、amount、posting_date、card_last4）
- [ ] 2.5 模組層級呼叫 `registry.register(SinopacV1Parser())`
- [ ] 2.6 更新 `backend/src/ccas/parser/banks/__init__.py` 加入 `from . import sinopac_v1`

## 3. 測試

- [ ] 3.1 建立測試用合成 PDF fixture（`backend/tests/fixtures/sinopac/` 下的有效帳單、缺失欄位帳單、非永豐帳單）
- [ ] 3.2 撰寫 `backend/tests/unit/parser/test_sinopac_v1.py` 單元測試（can_parse 正反例、parse 摘要提取、交易提取、錯誤處理）
- [ ] 3.3 執行 `uv run pytest tests/unit/parser/test_sinopac_v1.py -v` 確認全部通過

## 4. 文件更新

- [ ] 4.1 更新 `docs/user-guide.md` 新增永豐銀行設定說明（Gmail filter、PDF 密碼、banks.yaml 設定）
