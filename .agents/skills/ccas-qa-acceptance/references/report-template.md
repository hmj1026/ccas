# CCAS QA 驗收報告

- 日期: {{DATE}}
- 模式: {{MODE}}
- 耗時: {{TOTAL_DURATION}}

## 摘要

| 指標 | 數值 |
|------|------|
| 總 Phase 數 | {{TOTAL_PHASES}} |
| 通過 | {{PASS_COUNT}} |
| ERROR | {{ERROR_COUNT}} |
| VERIFICATION-ISSUE | {{VI_COUNT}} |
| 跳過 | {{SKIP_COUNT}} |

## 效能基準

| 項目 | 本次 | 上次 | 變化 |
|------|------|------|------|
| Pipeline 總時間 | {{PIPELINE_TIME}} | {{PREV_PIPELINE}} | {{DELTA_PIPELINE}} |
| 測試套件時間 | {{TEST_TIME}} | {{PREV_TEST}} | {{DELTA_TEST}} |
| Docker build 時間 | {{BUILD_TIME}} | {{PREV_BUILD}} | {{DELTA_BUILD}} |

## Phase 詳細結果

### Phase 0: 環境與憑證驗證
- 狀態: {{P0_STATUS}}
- 結果: {{P0_DETAIL}}

### Phase 1: Docker 基礎建設
- 狀態: {{P1_STATUS}}
- 結果: {{P1_DETAIL}}

### Phase 2: 資料庫重置
- 狀態: {{P2_STATUS}}
- 結果: {{P2_DETAIL}}

### Phase 3: Pipeline 全銀行執行
- 狀態: {{P3_STATUS}}
- 結果:

| 銀行 | Bills | Transactions | 耗時 | 備註 |
|------|-------|-------------|------|------|
| {{BANK}} | {{BILLS}} | {{TXNS}} | {{DURATION}} | {{NOTES}} |

### Phase 4: Telegram 通知邏輯驗證
- 狀態: {{P4_STATUS}}
- 結果: {{P4_DETAIL}}

### Phase 5: 後端測試套件
- 狀態: {{P5_STATUS}}
- Unit: {{UNIT_PASSED}} passed / {{UNIT_FAILED}} failed
- Integration: {{INT_PASSED}} passed / {{INT_FAILED}} failed
- E2E: {{E2E_PASSED}} passed / {{E2E_FAILED}} failed
- Coverage: {{COVERAGE}}%

### Phase 6: API 端點驗證
- 狀態: {{P6_STATUS}}
- 結果: {{API_PASS}}/{{API_TOTAL}} 端點通過

### Phase 7: 前端測試與視覺驗證
- 狀態: {{P7_STATUS}}
- Vitest: {{VITEST_PASSED}} passed / {{VITEST_FAILED}} failed
- Playwright: {{PW_PASSED}} passed / {{PW_FAILED}} failed

### Phase 8: 額外 QA 檢查點
- 狀態: {{P8_STATUS}}
- 結果: {{P8_DETAIL}}

## 問題清單

| # | Phase | 嚴重度 | 描述 |
|---|-------|--------|------|
| 1 | {{PHASE}} | {{SEVERITY}} | {{DESCRIPTION}} |

## 回歸分析

### 新增問題（本次新增）

（無 / 列表）

### 已解決問題（前次存在，本次消失）

（無 / 列表）

### 持續問題（兩次皆存在）

（無 / 列表）

## 後續行動

- [ ] 修復所有 ERROR 等級問題
- [ ] 調查 VERIFICATION-ISSUE 等級問題
- [ ] 更新效能基準

## DB Snapshot

```json
{{DB_SNAPSHOT}}
```

---

結論: {{CONCLUSION}}
