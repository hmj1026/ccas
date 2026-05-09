## 1. TDD 前置（RED）

- [x] 1.1 新增 `backend/tests/unit/parser/test_ctbc_ocr_postprocess.py`，覆蓋：
  - hyphen 正規化正例 3 筆（`ICP一統一超商`、`P一C`、`01一06`）
  - hyphen 保留反例 3 筆（`統一超商`、`統一時代`、`本行扣繳`）
  - 白名單替換 3 筆（`百鋼 → 百貨`、`鐵包 → 購物卡`、`錢包 → 購物卡`）
  - 空字串輸入回空字串
  - 先白名單後 hyphen 順序
- [ ] 1.2 新增 `backend/tests/integration/parser/test_ctbc_v1_ocr_regression.py`，對 2 份 `staging/CTBC/*.pdf` assert：
  - `TransactionItem.merchant` 不含「一」夾於 ASCII 字元間的 pattern
  - merchant 不含「百鋼」、「鐵包」等白名單已知錯字
- [x] 1.3 `cd backend && uv run pytest tests/unit/parser/test_ctbc_ocr_postprocess.py tests/integration/parser/test_ctbc_v1_ocr_regression.py -x` 確認 RED

## 2. 實作 ocr_postprocess 模組

- [x] 2.1 新增 `backend/src/ccas/parser/banks/ctbc/__init__.py`（若尚不存在）
- [x] 2.2 新增 `backend/src/ccas/parser/banks/ctbc/ocr_postprocess.py`：
  - Module-level `_BRAND_CORRECTIONS: dict[str, str]`（初版 ≥ 10 條）
  - `_HYPHEN_PATTERN = re.compile(r"(?<=[A-Za-z0-9])一(?=[A-Za-z0-9])")`
  - `normalize_ocr_merchant(raw: str) -> str`：先白名單 `str.replace` → 後 `_HYPHEN_PATTERN.sub("-", ...)`

## 3. 串接到 ctbc_v1.py

- [x] 3.1 在 `backend/src/ccas/parser/banks/ctbc_v1.py` 頂端 `from ccas.parser.banks.ctbc.ocr_postprocess import normalize_ocr_merchant`
- [x] 3.2 在構造 `TransactionItem` 前對 merchant 字串套 `normalize_ocr_merchant`
- [x] 3.3 重跑 1.3 測試 → GREEN

## 4. 手動驗收

- [ ] 4.1 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --from parse --to parse`
- [ ] 4.2 `sqlite3 backend/data/ccas.db "SELECT DISTINCT merchant FROM transactions WHERE bill_id IN (SELECT id FROM bills WHERE bank_code='CTBC') LIMIT 20;"` 肉眼檢查
- [ ] 4.3 `sqlite3 ... "SELECT COUNT(*) FROM transactions WHERE merchant LIKE '%一%' AND merchant GLOB '*[A-Za-z0-9]一[A-Za-z0-9]*';"` 應回 0

## 5. 回歸驗證

- [x] 5.1 `cd backend && uv run pytest -k ctbc -x`
- [x] 5.2 `cd backend && uv run pytest tests/integration/parser/ -x`
- [x] 5.3 在 `docs/e2e-user-guide-walkthrough.md` 問題 #2 狀態改 `archived`，`對應 change slug` 填 `fix-ctbc-parser-cjk-corruption`
- [x] 5.4 `openspec verify fix-ctbc-parser-cjk-corruption` 通過
