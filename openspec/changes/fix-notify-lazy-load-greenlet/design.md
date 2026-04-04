## Context

SQLAlchemy AsyncSession 在 `rollback()` 後 expire 所有 session-bound 物件。`bills` list 是在 session 中查詢的 ORM 物件，rollback 後若再存取屬性會觸發 lazy load，async 環境中需要 greenlet context（`greenlet_spawn`）才能執行同步 DB 操作。

## Goals / Non-Goals

**Goals:**
- notify job 在多個帳單通知時，單個失敗不影響後續帳單的處理
- 消除 `MissingGreenlet` exception

**Non-Goals:**
- 不更改 session 的 `expire_on_commit` 設定（會影響整個 pipeline）

## Decisions

**D1 — 在 for 迴圈最開始提前讀取所有需要的 ORM 屬性**

```python
for bill in bills:
    bill_id = bill.id
    bill_code = bill.bank_code
    bill_month = bill.billing_month
    try:
        ...
        await session.commit()
    except Exception as exc:
        await session.rollback()
        # 使用已緩存的 bill_id, bill_code, bill_month（不再存取 bill 物件）
```

這是現有的程式碼結構，問題在於 `bill.id` 等在 rollback 後的迭代中被重新存取。確保這些本地變數在 try 塊外且在任何 session 操作之前被賦值。

## Risks / Trade-offs

- [Risk] 如果 bill 在 for 迴圈前已 expire（例如某些 session 配置），第一個迭代的屬性存取也可能失敗 → Mitigation: 考慮用 `expire_on_commit=False` 的 sessionmaker，或在 `run_notify_job` 的開頭用 `await session.refresh(bill)` 重載所有 bills
