## Context

CCAS 管線架構已支援多銀行擴充：`banks.yaml` 定義銀行設定、`BankParser` 抽象介面提供統一 contract、`ParserRegistry` 負責自動發現。CTBC 是已上線銀行，SINOPAC 正在開發中。玉山銀行（ESUN, FSC code 808）為第三家待支援銀行。

使用者提供的玉山帳單郵件資訊：
- 寄件者：`estatement@esunbank.com`
- 主旨格式：`玉山銀行2026年02月信用卡電子帳單`
- PDF 密碼規則與 CTBC 相同（身分證字號），但使用獨立 env var

## Goals / Non-Goals

**Goals:**
- 玉山帳單可透過現有 5 階段管線（ingest -> decrypt -> parse -> classify -> notify）自動處理
- 遵循 CTBC 建立的 parser 模式（BankParser 繼承、registry 自動註冊、pdfplumber 解析）
- 提供 `PDF_PASSWORD_ESUN` 獨立密碼設定
- 有完整單元測試與整合測試覆蓋

**Non-Goals:**
- 不修改現有 pipeline / ingestor / decryptor 架構（已支援多銀行）
- 不實作 OCR（先確認玉山帳單是否需要，PDF 中商戶名稱若為文字則不需 OCR）
- 不做玉山銀行的帳單分期或特殊交易類型解析（v1 聚焦基本交易明細）
- 不處理紅利點數、年費等非消費類項目

## Decisions

### D1: Parser 辨識策略

**選擇**: 使用 PDF 首頁文字特徵辨識（關鍵字 `"玉山銀行"` + `"信用卡"`）。

**理由**: 與 CTBC 一致的模式。附件名稱在 parse 階段已不可用（只有 PDF path），故必須依賴 PDF 內容辨識。

**替代方案**: 使用 email metadata（寄件者）辨識 -- 但 parse 階段不存取 email 資訊，不可行。

### D2: 日期格式處理

**選擇**: 西元年（YYYY/MM/DD 或 YYYY-MM-DD）為主，若遇民國年則轉換。

**理由**: 玉山帳單 email 主旨使用西元年（`2026年02月`），推測 PDF 內容也以西元年為主。但仍需處理民國年 fallback 以應對格式差異。

### D3: 密碼環境變數命名

**選擇**: `PDF_PASSWORD_ESUN`，遵循 `PDF_PASSWORD_{BANK_CODE}` 既有模式。

**理由**: `Settings.get_pdf_password(bank_code)` 已實作動態 env var 查找，無需修改 config 層。

### D4: 檔案結構

```
backend/src/ccas/parser/banks/esun_v1.py      # parser 實作
backend/tests/unit/parser/test_esun_v1.py      # 單元測試
backend/tests/integration/parser/test_esun_v1_pdf.py  # 整合測試（合成 PDF）
```

**理由**: 完全對齊 CTBC 的檔案命名慣例（`{bank_code}_v1.py`）。`__init__.py` 已預留 `esun_v1` 的 import 行。

### D5: 合成測試 PDF

**選擇**: 使用 `fpdf2` 在整合測試中程式化產生玉山帳單格式 PDF。

**理由**: 不依賴真實帳單（含個資），可重複產生、可版控。CTBC 整合測試已採用此模式。

## Risks / Trade-offs

- **[PDF 格式未知]** -> 尚無實際玉山帳單 PDF 樣本，parser 的 regex 和欄位提取邏輯需待取得樣本後調整。**Mitigation**: v1 先以合理假設實作骨架，取得真實帳單後快速迭代。
- **[格式變動]** -> 銀行可能隨時改版帳單格式。**Mitigation**: 版本化 parser（v1/v2），registry fallback 機制已就緒。
- **[密碼值相同但 key 分開]** -> 使用者需在 `.env` 設定多個值相同的變數。**Mitigation**: 文件中說明可複製值；未來可考慮 alias 機制，但目前保持簡單。
- **[主旨格式差異]** -> Gmail filter 需精準匹配「玉山銀行」+「信用卡電子帳單」，避免誤 match 其他玉山通知信。**Mitigation**: filter 使用 `from:` + `subject:` 雙重過濾。
