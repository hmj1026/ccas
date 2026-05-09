# Design: UBOT Parser Real PDF Format

## Context

UBOT 帳單 PDF 從 pdfplumber 抽取的文字並非表格而是空白分隔的純文字，欄位意義需從位置推斷。既有 parser 僅支援理論的 `繳費截止日：...` 標籤格式，在所有真實 PDF 上失敗。

## Approach

採用「正則表達式定位錨點 + 位置推斷」策略：不依賴 table extraction（pdfplumber `extract_tables` 對此版 PDF 回傳欄位錯位的結果），改以行內錨點字串（`為您XX月份`、`已申請自動轉帳`、`優惠注意事項`）作為定位點。

### Summary Anchors

| 欄位 | 錨點 | Regex |
|---|---|---|
| billing_month | `為您(\d+)月份` + 結帳日 ROC 年 | `為您(\d{1,2})月份`、`(\d{2,3})/(\d{1,2})/\d{1,2}\s+[\d.]+%` |
| due_date | `已申請自動轉帳` | `(\d{2,3})/(\d{1,2})/(\d{1,2})\s+已申請自動轉帳` |
| total_amount | `優惠注意事項` | `^([\d,]+)\s+[\d,]+\s+[\d,]+\s+優惠` |
| zero-balance | `無需繳款` | literal substring |

### Transaction Regex

```python
_RE_UBOT_TXN_REAL = re.compile(
    r"^\+?\s*"                             # optional + (mobile payment marker)
    r"(\d{1,2}/\d{1,2})\s+"                # trans_date (MM/DD)
    r"(\d{1,2}/\d{1,2})\s+"                # posting_date (MM/DD)
    r"(.+?)\s+"                            # merchant (non-greedy)
    r"(-?[\d,]+)\s*$",                     # amount (signed, possibly comma-separated)
    re.MULTILINE,
)
```

Non-greedy merchant + end-anchor forces the engine to consume every other numeric-looking token (installment markers `02/12`, foreign amounts `600.00`, country codes `TW`/`JP`) as part of the merchant, leaving only the final NT amount at EOL.

### Card Header Tracking

```python
_RE_UBOT_CARD_HEADER = re.compile(r"(聯邦[^\n]*?卡)\s*－正卡\s*(\d{3,4})")
```

Scan line by line; when a header line is encountered, store `current_card` and attach to subsequent transactions until the next header.

## Trade-offs

- **Bug risk**: ambiguous `.+?` merchant may over-consume; mitigated by end-anchor and real PDF test cases.
- **Zero-balance path**: raises `ParseError` with `reason="zero-balance: 無需繳款"`, letting existing `parser/job.py` detection route to `parse_skipped`. Consistent with ESUN/SINOPAC handling.
- **Backward compat**: original regexes kept for existing unit tests (mocked 2026 formats).

## Alternatives Considered

1. **pdfplumber table extraction** — rejected: returns misaligned cells for UBOT's custom grid.
2. **Column-coordinate slicing** — rejected: brittle across multi-year layout drift.
