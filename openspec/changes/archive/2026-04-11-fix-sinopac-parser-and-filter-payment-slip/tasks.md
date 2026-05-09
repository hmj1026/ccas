# Tasks

## T1: 附件檔名黑名單過濾模組
- [x] T1.1 新增 `backend/src/ccas/ingestor/filters.py`：
  - [x] 定義 `ATTACHMENT_FILENAME_BLOCKLIST: dict[str, tuple[str, ...]] = {"SINOPAC": ("繳款聯",)}`
  - [x] 提供 `should_skip_attachment(bank_code: str, filename: str) -> bool`（substring match, case-insensitive）
- [x] T1.2 Unit test `backend/tests/unit/ingestor/test_filters.py`：
  - [x] SINOPAC `永豐銀行信用卡繳款聯.pdf` → True
  - [x] SINOPAC `永豐銀行信用卡帳單.pdf` → False
  - [x] CTBC 任何檔名 → False（無黑名單）

## T2: ingestor job 串接黑名單
- [x] T2.1 `backend/src/ccas/ingestor/job.py`：`_process_attachment` 於方法第一行呼叫 `should_skip_attachment(bank_code, attachment.filename)`；命中時 `summary.skipped_count += 1` 後 `return`（MUST NOT 呼叫 `find_existing_staged`、MUST NOT 下載）
- [x] T2.2 Integration test：fake Gmail 回傳一筆 `帳單.pdf` + 一筆 `繳款聯.pdf`，ingest 後 staged=1, skipped=1, DB 只剩一列 `帳單.pdf`

## T3: SinopacV1Parser 摘要擷取修正
- [x] T3.1 `backend/src/ccas/parser/banks/sinopac_v1.py`：`_RE_DUE_DATE` 改為 `r"繳[費款]截止日[：:]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})"`（冒號可選）
- [x] T3.2 `_extract_total_amount` 改為：
  - [x] 以 `re.search(r"臺幣\s+([\d,]+(?:\s+[\d,]+){6})", text)` 抽取 `臺幣` 列七個數字
  - [x] 取 index 5（本期應繳總金額，跳過 `臺幣`=col0、上期=1、已繳=2、新增=3、循環=4、違約=5、本期應繳=6 → wait 實際上 group(1) 已剔除「臺幣」，7 個數字的 index 為 5）
  - [x] 無法 match 時 fallback 嘗試舊的關鍵字 regex（向後相容）
- [x] T3.3 Unit test 覆蓋：
  - [x] 冒號格式 due_date
  - [x] 無冒號格式 due_date（真實 SINOPAC 格式）
  - [x] 臺幣列七欄抽取本期應繳總金額

## T4: SinopacV1Parser 交易擷取修正
- [x] T4.1 `_TRANSACTION_HEADER_KEYWORDS = ("入帳", "臺幣金額")`
- [x] T4.2 新增 `_RE_SINOPAC_TXN_LINE = re.compile(r"^(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2})\s+(\d{4})\s+(.+?)\s+(-?[\d,]+)\s*$", re.MULTILINE)`
- [x] T4.3 `_extract_transactions_text()` 優先嘗試新 regex；保留舊 regex 為 fallback
- [x] T4.4 `_parse_transaction_row`：支援 5 欄 `[入帳日, 卡號, 帳單說明, 臺幣金額, ...]`（table 模式）
- [x] T4.5 Unit test：
  - [x] 正常消費行（含卡號末四碼）
  - [x] 負數退款行
  - [x] 合法忽略欄位不符的行

## T5: 零額歷史帳單處理
- [x] T5.1 `SinopacV1Parser.parse()` 在 `_extract_summary()` 前先檢查 `無需繳款`，命中則 `raise ParseError("zero-balance historical bill", reason="no amount / due date")`
- [x] T5.2 `backend/src/ccas/parser/job.py`（或 application）：catch `ParseError` 且 reason 或 message 包含 `zero-balance` 時，將該筆計入 `skipped_count` 而非 `failed_count`（若現有 job 未區分，至少用 `logger.info` 標記）
- [x] T5.3 Unit test：零額 PDF 樣本觸發 ParseError，訊息包含 `zero-balance`

## T6: End-to-end 驗證
- [x] T6.1 `cd backend && uv run python -m ccas.pipeline --bank SINOPAC --force`
  - [x] 預期：ingest staged=58（原先 118 扣掉 59 繳款聯）/ skipped=59（繳款聯）
  - [x] parse staged=58，failed=0（1 零額 skipped）
  - [x] bills 新增 58 列、transactions 非空
- [x] T6.2 `cd backend && uv run python -m ccas.pipeline --bank SINOPAC`（Run B，冪等驗證）
  - [x] ingest staged=0, skipped=58
  - [x] parse 0 new
- [x] T6.3 `./scripts/dev-test.sh` 全綠
- [x] T6.4 `./scripts/dev-lint.sh` 無 error
- [x] T6.5 `sqlite3 data/ccas.db "SELECT COUNT(*) FROM bills WHERE bank_code='SINOPAC';"` ≥ 58
