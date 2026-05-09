## Context

`CathayV1Parser._extract_transactions` 走「table first, text fallback」路徑：

```
_extract_transactions
 ├─ _extract_transactions_table
 │   └─ _is_transaction_table (header keyword check)
 │       ↓ (miss)
 └─ _extract_transactions_text
     ├─ _RE_TRANSACTION_LINE      (date date merchant amount)
     └─ _RE_TRANSACTION_LINE_SIMPLE (date merchant amount)  ← fallback
```

E2E 跑完 107 份 CATHAY PDF 後總共只拿到 90 筆，且內容像 `帳單分期 12-12 33,293 2,774 6.00%`——證據指向：

1. `_is_transaction_table` header keyword 比對在 CATHAY 真實 PDF 上命中率 = 0，因此 fallback 到 text。
2. `_RE_TRANSACTION_LINE` 失配，fallback 到 `_RE_TRANSACTION_LINE_SIMPLE`。
3. `_RE_TRANSACTION_LINE_SIMPLE` 可能在「帳單分期」段尾吃到形如 `YYY/MM/DD 帳單分期 12-12 33293` 的模式，產生 ghost row；真正消費行反而因格式差異沒被命中。

目前既有 fixtures（`fixtures/cathay/*.pdf`）涵蓋新版 layout（105~115 年），但 E2E 問題 staging 中有 106 年（10603）等舊期 PDF，layout 與 fixture 不同，fixture 不會抓到這個 regression。

## Goals / Non-Goals

**Goals:**
- 對 107 份 CATHAY staging PDF 重跑 parse 後，`transactions` 總筆數 ≥ 500（粗估：平均每期 5 筆以上）。
- `TransactionItem.merchant` 不再出現「帳單分期」、「紅利」等欄位字樣。
- 既有新版 layout fixture 的測試不回歸。

**Non-Goals:**
- 不改 classifier / category 邏輯。
- 不動 `_extract_summary`, `_extract_billing_month`, `_extract_due_date`, `_extract_total_amount`。
- 不重寫 pdfplumber table parser；只擴充 header keyword set 與加段落過濾。

## Decisions

### D1：Header keyword 改為 keyword set，「任一命中即通過」

**選擇**：`_TRANSACTION_HEADER_KEYWORDS` 從 `all(kw in header_text)` 改為兩層：
- **amount 欄**（必要）：header 含 `金額` OR `新臺幣金額` OR `款項`。
- **date 欄**（必要）：header 含 `交易日` OR `消費日` OR `日期`。

兩類各至少一個命中才認為是 transaction table。

**理由**：
- CATHAY 不同期 PDF header 字樣不統一（新版「交易日 入帳日 卡號末四碼 消費明細 新臺幣金額」、舊版可能只有「消費日 消費明細 金額」），硬 `all` 單一 keyword set 命中率低。
- 分兩類（date-ish + amount-ish）避免把其他表（例如「分期資訊」表，可能只含「金額」但沒日期）誤判。

**Alternatives:**
- (A) 改用欄位數量 heuristic（如「header 有 ≥ 4 欄 且其中一欄含日期字樣」）：過於寬鬆，容易吃到其他 layout 表格。
- (B) 為每期 PDF hard-code header mapping：維護負擔大，加新年份就要改 code。

### D2：Text 擷取前做 section-based cropping

**選擇**：在 `_extract_transactions_text` 對每頁 `extract_text()` 的結果先做段落裁切：

```python
_NON_TRANSACTION_SECTION_ANCHORS = (
    "帳單分期",
    "紅利點數",
    "優惠回饋",
    "本期回饋",
    "累積紅利",
    "循環信用",
)

def _crop_transaction_section(text: str) -> str:
    """Cut off everything from the first non-transaction section anchor."""
    earliest = len(text)
    for anchor in _NON_TRANSACTION_SECTION_ANCHORS:
        idx = text.find(anchor)
        if 0 <= idx < earliest:
            earliest = idx
    return text[:earliest]
```

**理由**：
- CATHAY PDF 結構上「消費明細」區塊永遠在前，後面才是「帳單分期 / 紅利 / 回饋」說明。以 anchor 切斷後，regex 只掃明細區，ghost row 直接消失。
- 實作成本低，不需重寫 regex。

**Alternatives:**
- (A) 收緊 `_RE_TRANSACTION_LINE_SIMPLE` 讓 merchant 必須為非數字開頭：對混中英文商店名較安全，但對「7-ELEVEN」這類數字開頭店名會回歸。
- (B) 要求金額 ≤ 某閾值過濾：語意錯誤，真實消費可能超過百萬。

### D3：Fallback 順序反轉 — 先 SIMPLE 後 FULL 仍保留既有順序

**選擇**：維持「full format 先，simple format 後」，**不變**。

**理由**：既有測試 fixture 驗證了 full 能抓新版 grid layout；反轉會造成回歸。D2 的 cropping 已足以解決 ghost row。

## Risks / Trade-offs

- **[R1]** Section anchor 命中過激進，把合法交易也切掉：若某 PDF 消費段裡真的出現「紅利」二字（如商店名「紅利大賣場」），整段後面會被誤切。→ Mitigation：anchor 採整詞前綴限定（例如 `紅利點數` 不 match `紅利大賣場`），且 TDD fixture 至少納入一份有「紅利」字樣商店的 PDF 驗證。

- **[R2]** Header keyword set 放寬後，把非交易表（如「本期應繳分析」表）誤認為交易表：→ Mitigation：保留「date-ish + amount-ish 各至少一個」雙欄要求；並在 TDD 新增一個 negative case：只有金額欄沒日期欄的表不應被解為交易表。

- **[R3]** 舊期 PDF（106~108 年）真正消費行的正則 pattern 可能與新版差異大，光靠 cropping + keyword 放寬不夠：→ Mitigation：**在 TDD RED 階段先跑一份舊期 PDF 確認 regex 命中率**；若 < 預期，則在同一 change 內再擴充 `_RE_TRANSACTION_LINE` 一個變體，不 defer 到後續 change。

## Migration Plan

1. 先跑 TDD RED：新增舊期 PDF fixture → 寫測試「至少捕捉 N 筆交易 且不含分期/紅利字樣」→ 確認 FAIL。
2. 改 `_is_transaction_table`：keyword set 分兩類。
3. 改 `_extract_transactions_text`：加 `_crop_transaction_section` 前置。
4. 重跑測試 GREEN。
5. 在本機對 `backend/data/staging/CATHAY/*.pdf` 全部 107 份跑 `pipeline --bank CATHAY --from parse --to parse`，record `parsed_rows` 總數當作驗收指標（設定下限 500）。
6. 無需 DB migration；已寫入的錯誤 rows 由使用者決定是否重跑 pipeline。
7. Rollback：revert 單檔即可。

## Open Questions

- **OQ1**：要不要在同一 change 修復「分類全未分類」問題（Issue #3）？結論：**不要**——分類是獨立的 classifier 問題，應在 `fix-classify-rules-not-matching` 處理。
- **OQ2**：要不要同步把同類 heuristic 套用到其他 7 家銀行 parser？結論：**不要**——每家 layout 不同，應該由各自的 E2E 回歸驅動獨立 change。
