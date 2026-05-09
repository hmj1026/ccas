## Context

`run_ingestion_job()` 在 `_fetch_active_banks()` 後若無 banks，進入 for 迴圈零次，直接回傳空的 `IngestionSummary`。pipeline 輸出 JSON 顯示所有 counts 均為 0，但沒有任何說明。

## Goals / Non-Goals

**Goals:**
- 無 active banks 時，ingest stage 在 summary.errors 中加入診斷訊息，並寫入 WARNING log

**Non-Goals:**
- 不讓 pipeline 以非零 exit code 退出（0 banks 不是「錯誤」）
- 不自動執行 bank sync（側效應太大）

## Decisions

**D1 — 在 `run_ingestion_job()` 加入早退警告**

```python
banks = await _fetch_active_banks(session, options)
if not banks:
    msg = "[Ingest] 未找到任何啟用的銀行設定。請先執行 python -m ccas.tools.bank_configs --apply 初始化銀行設定。"
    logger.warning(msg)
    summary.errors.append(msg)
    return summary
```

此做法最小侵入，不影響正常路徑。

## Risks / Trade-offs

- [Risk] 用戶看到 errors 陣列有內容可能誤以為是嚴重錯誤 → Mitigation: 訊息明確說明是設定問題，並提供具體指令
