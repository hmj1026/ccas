## Context

UBOT parser 對每筆抽到的 row 無條件構造 `TransactionItem`。E2E 實測在 DB 看到「現金回饋入帳」、「紅利折抵」等行與正常消費混雜。結構與 SINOPAC Change #5 同類但 keyword 不同。

## Goals / Non-Goals

**Goals:**
- 回饋/折抵/退款行 MUST NOT 進入 `transactions`。
- 正常消費不回歸。

**Non-Goals:**
- 不保留 cashback metadata。
- 不與 SINOPAC parser 共用 helper（per-bank ownership）。

## Decisions

### D1：與 SINOPAC Change 同構，但 per-bank 獨立

**選擇**：複製 filter 邏輯到 `ubot_v1.py`，不抽取 shared helper。

**理由**：
- 每家 PDF 樣本形態不同，未來若任一家需微調不會牽動另一家。
- 目前只有 2 家需要此類 filter，重複成本低於抽象化成本。
- 若未來第 4 家也需要再考慮 refactor 到 shared module。

### D2：Keyword set 採並集不採 regex

**選擇**：以 tuple 常數存 keyword，迭代 `merchant.startswith(kw) or merchant == kw` 判斷。

**理由**：regex 過度彈性不需要；startswith 對前綴判斷直觀。

### D3：負金額條件同樣保留

**選擇**：`amount < 0` 任一命中即算 cashback，不與 keyword 綁定。

**理由**：PDF 退款標示不一致；金額為負是最可靠的 invariant。

## Risks / Trade-offs

- **[R1]** 商家名含 keyword：如「紅利折扣店」— mitigation：前綴匹配 + TDD 正反例覆蓋
- **[R2]** Keyword 覆蓋率：新版 UBOT 帳單若用不同字樣會漏 — mitigation：後續 PR 擴充

## Migration Plan

1. TDD RED：fixture + 單元測試
2. 實作 filter
3. 重跑 `pipeline --bank UBOT --from parse`
4. 無 DB migration

## Open Questions

無。
