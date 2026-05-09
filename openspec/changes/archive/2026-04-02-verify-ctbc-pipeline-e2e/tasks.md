## 1. 自動化測試驗證

- [x] 1.1 執行後端單元測試 `uv run pytest tests/unit/ -v --tb=short`，確認全部 PASS (312 passed, 1.60s)
- [x] 1.2 執行後端整合測試 `uv run pytest tests/integration/ -v --tb=short`，確認全部 PASS (106 passed, 4.59s)
- [x] 1.3 執行後端 E2E 測試 `uv run pytest tests/e2e/ -v --tb=short`，確認全部 PASS (7 passed, 0.47s)
- [x] 1.4 執行覆蓋率報告 `uv run pytest --cov --cov-report=term-missing`，確認核心模組 > 80% (425 passed, 81.95% coverage)
- [x] 1.5 執行前端測試 `npm run test`，確認全部 PASS (6 files, 26 tests, 2.11s)

## 2. 真實 CTBC Pipeline 執行

- [x] 2.1 執行 CTBC pipeline -- 發現並修正 2 個 bug: (1) pikepdf 需 allow_overwriting_input=True (2) parser 需支援真實 ROC 格式。修正後: ingest=1, decrypt=1, parse=1, classify=15
- [x] 2.2 DB 驗證: Bill(2026-03, amount=2967, due=2026-03-28), 15 筆交易，金額合計=2967 與帳單一致。merchant 為空（PDF 圖片化限制）
- [x] 2.3 去重複驗證: 再次執行 parse skipped=1，DB 仍只有 1 Bill + 15 Transactions，無重複

## 3. API 端點驗證

- [x] 3.1 Overview: total_spending=2967, total_unpaid=2967
- [x] 3.2 Bills: CTBC 2026-03, amount=2967, due=2026-03-28, pdf_url 存在
- [x] 3.3 Transactions: 15 筆, 分頁正確 (total_pages=3)
- [x] 3.4 Categories: 未分類=2967 (merchant 為空故全歸未分類)
- [x] 3.5 Banks: CTBC total=2967, bank_name=中國信託
- [x] 3.6 CSV: UTF-8 BOM, 中文欄位名, 資料正確

## 4. 前端報表驗證

- [x] 4.1 前端 vitest 26 tests PASS (Task 1.5 已驗證)，API 回應格式與前端 types.ts 一致
- [x] 4.2 Bills API 回傳 bank_name/is_paid/pdf_url 欄位完整，前端可渲染
- [x] 4.3 Transactions API 分頁/篩選正常，pagination metadata 完整
- [x] 4.4 Analytics API trend/categories/banks 回傳正確結構

## 5. 問題修正

- [x] 5.1 修正 2 個 bug: (1) decrypt.py: pikepdf allow_overwriting_input=True (2) ctbc_v1.py: 支援真實 ROC 格式 + ctbc.tw 識別
- [x] 5.2 更新 test_decrypt.py mock 函數接受 **kwargs；全部 425 tests PASS，lint clean
