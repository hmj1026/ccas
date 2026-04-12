## Context

SINOPAC parser 目前對每筆抽到的 row 無條件構造 `TransactionItem`。E2E 實測後在 DB 看到退款行（商家如「退款-XX」或金額為負）與正常消費行混雜，前端與 classifier 皆無從分辨。

## Goals / Non-Goals

**Goals:**
- 退款/退費/沖銷/取消行 MUST NOT 進入 `ParseResult.transactions`。
- 正常消費行不回歸。
- 提供可擴充的 keyword list，後續新增樣本不必改邏輯。

**Non-Goals:**
- 不改 bill summary。
- 不保留 refund row 到 DB（本 change 先丟棄，後續若需對帳再開 change 加 metadata 欄位）。

## Decisions

### D1：多條件 OR 判斷（任一命中即視為退款）

**選擇**：`_is_refund_row` 三條件任一 True 即視為退款：
1. merchant 含 refund keyword
2. amount < 0
3. raw line 行首 `(-)` 或全形 `－`

**理由**：
- 不同年份/版面退款表示法不同，單條件易漏。
- False positive 風險低：三條件都指向金錢回補語意。

### D2：Refund keyword 採前綴 anchoring

**選擇**：refund keyword 僅在 merchant 字串**開頭或全字**匹配才算命中，避免「取消授權費用 100」之類真實消費（若某日真出現）被誤判。

**理由**：SINOPAC 退款行的商家字樣通常是「退款-原消費日」、「沖銷」單字開頭，不會夾在正常商家名中段。

**Alternatives:**
- (A) substring match：簡單但 false positive 高。
- (B) regex 全名匹配：過嚴，新樣本需常改。

### D3：Refund row 不入 DB

**選擇**：filter 掉後不保留 metadata。

**理由**：目前 `ParseResult` schema 無 metadata 欄位，擴充需跨 bank-parser-contract spec 改動，超出本 change scope。

## Risks / Trade-offs

- **[R1]** 誤刪合法消費：商家真名含「退款」字樣。→ Mitigation：keyword 採前綴匹配 + TDD fixture 覆蓋正反例。
- **[R2]** 新版 SINOPAC 帳單改用不同退款字樣：需後續 PR 擴充 keyword。

## Migration Plan

1. TDD RED：fixture 含退款段的 PDF + 構造 text 單元測試。
2. 實作 `_is_refund_row` 與 filter 串接。
3. 重跑 `pipeline --bank SINOPAC --from parse`，抽樣驗證。
4. 無 DB migration。

## Open Questions

- **OQ1**：是否需要對帳 metadata？決定：**不做**，留給獨立 change。
