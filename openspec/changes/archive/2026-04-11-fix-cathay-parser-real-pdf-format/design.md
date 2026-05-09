# Design: Fix CATHAY Parser Real PDF Format

## Context
真實國泰世華信用卡帳單 PDF 跨多種佈局（108~115 年），與測試 fixture 假設的 `繳款截止日：YYYY/MM/DD` 格式差異顯著。同時 Gmail 同郵件附帶「繳款聯」付款憑證，並非帳單資料。

## Observed Layouts
| 年份 | 首頁 keyword | billing_month anchor | due_date anchor |
|-----|-------------|---------------------|-----------------|
| 106-111 | 國泰世華（部分被 CID 遮蔽） | `以下為您YYY年MM月份的信用卡電子帳單` | `繳款截止日(遇假日順延) ROC/MM/DD` |
| 112+ | 國泰世華（多被 CID 遮蔽） | （grid，無明顯 header） | `您的新臺幣帳款將於 ROC/MM/DD` |
| 115+ | 國泰世華（多被 CID 遮蔽） | `信用卡帳單 YYY年MM月` | `您的新臺幣帳款將於 ROC/MM/DD (遇假日順延)` |

## Decisions

### D1: can_parse 掃描全部頁面
Page 0 的收件人姓名被 CID 字型遮蔽導致 `extract_text()` 無法還原「國泰世華」字串。其他頁面則可正常 extract。

**實作**：`can_parse` 改為 `"\n".join(page.extract_text() or "" for page in pdf.pages)` 後再檢查 keywords。與 UBOT 同策略，效能差距 <50ms，可接受。

### D2: 繳費截止日多錨點
新增兩組 regex：
```python
_RE_DUE_DATE_PAREN = re.compile(r"繳款截止日\(遇假日順延\)\s*(\d{2,3})/(\d{1,2})/(\d{1,2})")
_RE_DUE_DATE_DEBIT = re.compile(r"帳款將於\s*(\d{2,3})/(\d{1,2})/(\d{1,2})")
```
後援順序：既有 `繳[費款]截止日：` → `繳款截止日(遇假日順延)` → `帳款將於`。

### D3: 帳單月份多錨點
```python
_RE_BILLING_MONTH_REAL = re.compile(r"以下為您(\d{2,3})年(\d{1,2})月份")
_RE_BILLING_MONTH_HEADER = re.compile(r"信用卡帳單\s*(\d{2,3})年\s*(\d{1,2})月")
```
後援順序：既有西元 `YYYY年MM月` → 新 `以下為您` 錨點 → 新 `信用卡帳單 YYY年MM月` → 既有 `(YYY)年(MM)月`（最泛用）。

### D4: 繳款聯黑名單
`ATTACHMENT_FILENAME_BLOCKLIST["CATHAY"] = ("繳款聯",)` — 同 SINOPAC/TAISHIN 模式，66 個歷史付款憑證附件會在 ingest 階段早期被略過。

## Trade-offs
- **Alternative considered**：改用 OCR 取得 page 0 正確姓名字串 → 複雜度高且跨版本效果不一致，不採納
- **Alternative considered**：用 PDF metadata 辨識發卡行 → 國泰世華多版 PDF 無一致 Producer 欄位，不可靠

## Verification
- Unit: 三組 fixture 對應三種佈局，每組驗證 billing_month / due_date / total_amount
- Integration: `uv run python -m ccas.pipeline --bank CATHAY --from parse` → failed=0
