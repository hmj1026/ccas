## Context

CCAS 管線架構已支援多銀行擴充：`banks.yaml` 定義銀行設定、`BankParser` 抽象介面提供統一 contract、`ParserRegistry` 負責自動發現。CTBC 是唯一已實作銀行，SINOPAC/ESUN/UBOT 已建立 spec 但尚未實作。台新銀行（TAISHIN, FSC code 812）需成為下一個加入的銀行。

使用者提供的台新帳單郵件資訊：
- 寄件者：`webmaster@bhurecv.taishinbank.com.tw`
- 主旨格式：`台新信用卡電子帳單 YYYY年M月`
- PDF 密碼規則：身分證字號後 2 碼 + 生日月日 4 碼（共 6 碼，與 CTBC 不同）

## Goals / Non-Goals

**Goals:**
- 台新帳單可透過現有 5 階段管線（ingest → decrypt → parse → classify → notify）自動處理
- 遵循 CTBC 建立的 parser 模式（BankParser 繼承、registry 自動註冊、pdfplumber 解析）
- 提供 `PDF_PASSWORD_TAISHIN` 獨立密碼設定
- 有完整單元測試覆蓋

**Non-Goals:**
- 不修改現有 pipeline / ingestor / decryptor 架構（已支援多銀行）
- 不實作 OCR（先確認台新帳單是否需要，PDF 中商戶名稱若為文字則不需 OCR）
- 不做台新銀行的帳單分期或特殊交易類型解析（v1 聚焦基本交易明細）

## Decisions

### D1: Parser 辨識策略

**選擇**: 使用 PDF 首頁文字特徵辨識（關鍵字 `"台新"` + `"信用卡"`）。

**理由**: 與 CTBC 一致的模式。附件名稱在 parse 階段已不可用（只有 PDF path），故必須依賴 PDF 內容辨識。

### D2: 日期格式處理

**選擇**: 西元年（YYYY/MM/DD 或 YYYY-MM-DD）為主，若遇民國年則轉換。

**理由**: 台新帳單可能使用西元年或民國年，parser 應同時處理。需取得實際 PDF 樣本後確認。

### D3: 密碼環境變數命名

**選擇**: `PDF_PASSWORD_TAISHIN`，遵循 `PDF_PASSWORD_{BANK_CODE}` 既有模式。

**理由**: `Settings.get_pdf_password(bank_code)` 已實作動態 env var 查找，無需修改 config 層。密碼規則（身分證字號後 2 碼 + 生日月日 4 碼）與 CTBC 不同，需在文件中特別說明。

### D4: 檔案結構

```
backend/src/ccas/parser/banks/taishin_v1.py    # parser 實作
backend/tests/unit/parser/test_taishin_v1.py    # 單元測試
backend/tests/fixtures/taishin/                 # 測試用合成 PDF
```

**理由**: 完全對齊 CTBC 的檔案命名慣例（`{bank_code}_v1.py`）。

### D5: 合成測試 PDF

**選擇**: 使用 `fpdf2` 在 test fixture 中程式化產生台新帳單格式 PDF。

**理由**: 不依賴真實帳單（含個資），可重複產生、可版控。CTBC 測試已採用此模式。

## Risks / Trade-offs

- **[PDF 格式未知]** → 尚無實際台新帳單 PDF 樣本，parser 的 regex 和欄位提取邏輯需待取得樣本後調整。**Mitigation**: v1 先以合理假設實作骨架，取得真實帳單後快速迭代。
- **[格式變動]** → 銀行可能隨時改版帳單格式。**Mitigation**: 版本化 parser（v1/v2），registry fallback 機制已就緒。
- **[密碼規則不同]** → 台新密碼規則（身分證後 2 碼 + 生日月日 4 碼）與其他銀行不同，使用者需注意。**Mitigation**: 文件中明確說明密碼組成規則。
