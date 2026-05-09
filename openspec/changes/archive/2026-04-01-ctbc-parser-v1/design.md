## Context

CCAS parser 框架已定義：
- `BankParser` 抽象介面（`can_parse()` + `parse()`）
- `ParseResult` / `TransactionItem` frozen dataclasses
- `_ParserRegistry` 全域 singleton，以 `(bank_code, version)` 為 key
- `run_parse_job()` 自動解析 status="decrypted" 的附件

CTBC（中國信託）帳單 PDF 特性：
- 密碼保護（身分證字號全碼），解密由 upstream decryptor 處理
- 表格式交易明細
- 頁面結構待樣本 PDF 確認後微調

## Goals / Non-Goals

**Goals:**
- 實作可正確解析 CTBC 帳單 PDF 的 v1 parser
- 提取帳單摘要（billing_month, total_amount, due_date）
- 提取所有交易明細（trans_date, merchant, amount, card_last4 等）
- 透過 module-level registration 自動註冊到全域 registry
- 單元測試覆蓋率 >= 80%

**Non-Goals:**
- 不處理 CTBC 以外銀行的帳單
- 不修改 parser 框架本身（base.py, registry.py, job.py）
- v1 先聚焦 TWD 交易；外幣交易與分期付款的結構預留但可不完整
- 不建立真實 PDF 的 test fixture（使用合成資料）

## Decisions

### D1: 使用 pdfplumber 為主要解析工具

pdfplumber 原生支援 table extraction，且已在 pyproject.toml 依賴中。tabula-py 需要 Java runtime，作為備援但不在 v1 使用。不採用純 regex 文字擷取，因為帳單是表格結構。

**Alternatives considered:**
- tabula-py：需 Java，部署複雜度高
- PyMuPDF (fitz)：快但 table extraction 較弱
- 純 regex：脆弱，對格式變動敏感

### D2: Parser 分三層 pure function

```
can_parse(pdf) -> _identify(text: str) -> bool
parse(pdf)     -> _extract_summary(pages: list[pdfplumber.Page]) -> tuple[str, int, date]
               -> _extract_transactions(pages: list[pdfplumber.Page]) -> tuple[TransactionItem, ...]
```

- `_identify(text)`: 接收第一頁 `page.extract_text()` 結果，回傳是否為 CTBC 帳單
- `_extract_summary(pages)`: 回傳 `(billing_month: "YYYY-MM", total_amount: int, due_date: date)`
- `_extract_transactions(pages)`: 回傳 frozen `TransactionItem` tuple
- class name: `CtbcV1Parser(BankParser)`
- import: `from ccas.parser.registry import registry`

每個 `_extract_*` 方法為 pure function，接收 pdfplumber Page 物件，回傳值物件。好處：
- 各層可獨立單元測試
- 符合 SLAP 原則（Single Level of Abstraction）
- 測試不需要真實 PDF，可用文字 fixture 測試內部邏輯

### D3: 測試使用合成 fixture

**單元測試**：使用純文字常數（模擬 pdfplumber 提取出的文字/表格資料），測試 `_identify()`、`_extract_summary()`、`_extract_transactions()` 等內部方法。

**整合測試**：使用 `fpdf2`（dev dependency）程式化產生模擬 CTBC 帳單格式的合成 PDF，測試完整的 `can_parse()` -> `parse()` -> `ParseResult` 流程。pikepdf 用於解密，不適合從零產生 PDF。

不提交含 PII 的真實帳單 PDF 到 repo。

### D4: Module-level 自動註冊

`ctbc_v1.py` 底部執行 `registry.register(CtbcV1Parser())`。`banks/__init__.py` 加入 `import ccas.parser.banks.ctbc_v1`。parse job 啟動前 import `ccas.parser.banks` 即可自動註冊。

**測試隔離**：module-level registration 會在 import 時產生 side effect。測試 conftest.py 需提供 `autouse` fixture 在每個測試前後清空 registry，避免跨測試污染。

**Alternatives considered:**
- 手動在 job.py 中 register：違反開放封閉原則，每加一個 parser 都要改 job.py
- 使用 importlib 自動掃描：過度工程化，目前 parser 數量少

### D5: 迭代式版本策略

v1 處理最常見格式：
- TWD 帳單摘要（繳費截止日、應繳總額）
- TWD 交易明細（交易日、入帳日、商家、金額、卡號末四碼）
- 多頁表格延續

後續可擴充：
- 外幣交易（currency, original_amount）
- 分期付款（installment_current, installment_total）
- 格式大幅變更時建立 v2

### D6: CTBC 帳單格式辨識策略

`can_parse()` 讀取 PDF 第一頁文字，檢查是否包含特徵標記（如「中國信託」+「信用卡」相關關鍵字）。僅做格式辨識，不執行完整解析。

## Error Handling Policy

- **Mandatory fields**: `billing_month`, `total_amount`, `due_date` — 缺任一欄位 raise `ParseError`，訊息包含缺失欄位名稱
- **Optional fields**: `card_last4`, `posting_date` — 缺則 skip（該 TransactionItem 的對應欄位為 None），log WARNING
- **交易行解析失敗**：單筆交易行無法解析時 log WARNING 並跳過該行，不中斷整份帳單解析
- **Logger**: `logging.getLogger(__name__)`

## Risks / Trade-offs

- **[PDF 格式變動]** CTBC 可能隨時更新帳單格式。Mitigation: parser 版本化機制已就緒，格式變動時建立 v2。
- **[合成 fixture 與真實差異]** 合成 PDF 可能無法完全模擬真實帳單的 pdfplumber 解析行為。Mitigation: 使用者放入真實 PDF 後進行手動驗證，再根據差異調整 parser。
- **[pdfplumber table extraction 品質]** 部分 PDF 的表格邊界不明確，pdfplumber 可能誤判。Mitigation: 提供 `table_settings` 參數微調，或 fallback 到文字行解析。
