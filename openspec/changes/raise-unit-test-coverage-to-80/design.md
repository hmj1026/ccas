## Context

CCAS 後端的 unit 覆蓋率目前為 71.4%（閘門 70%）。`openspec/specs/test-infrastructure/spec.md` 已聲明「最低門檻 80%」，但 `pyproject.toml` 的 `fail_under` 與 CI 腳本實際執行時仍為 70%——實作落後 spec 10 個百分點。

問題分布：
- **0% (8 模組)**：`api/routers/setup/{banks,gmail,login_credentials,secrets}.py`、`api/routers/{staged_attachments,transactions_edit}.py`（皆有完整 integration tests）；`tools/categories.py`、`tools/reclassify.py`（完全無測試）
- **< 50% (10 模組)**：pipeline/progress、pipeline/worker、bot/queries、scheduler/jobs、classifier/staging、classifier/user_rules、decryptor/job、ingestor/credentials、ingestor/job、parser/staging
- **50–79% (7 模組)**：tools/seed_bank_settings、parser/job、parser/banks/sinopac_v1、storage/database、parser/banks/taishin_v1、classifier/rules

## Goals / Non-Goals

**Goals:**
- 所有非 omit 模組的 unit 覆蓋率達 ≥ 80%
- `pyproject.toml` `fail_under` 由 70 → 80
- CI `backend-test` job 與 `pre-push.sh` 閘門同步更新
- 6 個純 integration-tested router 進入 omit list（與既有 omit 慣例一致）
- `tools/categories.py`、`tools/reclassify.py` 從無測試到 ≥ 80%

**Non-Goals:**
- 提升 integration test 覆蓋率（整合測試已獨立運行，不計入閘門）
- E2E 測試補強（另有 e2e-pipeline-tests spec 管轄）
- 修改被測程式碼本身的行為（純測試補強，不改功能）
- 100% coverage（80% 為品質/維護成本的均衡點）

## Decisions

### D1：Setup router 加入 omit list（而非補 unit mock）

**選擇**：將 `api/routers/setup/*.py`、`staged_attachments.py`、`transactions_edit.py` 加入 `[tool.coverage.run] omit`。

**理由**：這些 router 的核心邏輯（DB I/O、加密、OAuth）高度耦合 FastAPI 的 `Depends` 注入，unit mock 的信噪比極低（mock 深度 > 實際邏輯行數）。現行的 integration tests（`test_setup_banks_router.py`、`test_staged_attachments.py` 等）已完整覆蓋成功/失敗路徑。

**放棄的替代方案**：補 unit tests + 大量 MagicMock — 維護成本高、易成 mock 陷阱，且不符現行「router 歸 integration」慣例（見既有 omit list 的 analytics/overview/pipeline/transactions/settings）。

### D2：補強順序 — 以高 ROI 為先

優先補強「行數多、覆蓋率低」的核心業務模組：
1. `pipeline/worker.py`（128行、41%）— 排程核心
2. `ingestor/job.py`（225行、54%）— 主進件流程
3. `decryptor/job.py`（100行、47%）— 解密協調
4. `classifier/user_rules.py`（78行、47%）— 使用者規則評估
5. `parser/job.py`（139行、62%）+ bank parsers（sinopac/taishin）
6. `scheduler/jobs.py`、`bot/queries.py`、剩餘低覆蓋模組

### D3：Mock 策略

- **async DB session**：使用 `MagicMock` + `AsyncMock` 搭配 `spec=AsyncSession`（現行慣例，避免 `MissingGreenlet` 連鎖）
- **外部服務**（Gmail、Telegram、Redis/RQ）：`respx` mock HTTP，`unittest.mock.patch` mock SDK 呼叫
- **Settings**：需補全有時效欄位（`timeout`、`cooldown_days` 等），避免 `MissingGreenlet` 

### D4：coverage gate 更新點

`fail_under = 80` 需在 3 處同步：
1. `backend/pyproject.toml` → `[tool.coverage.report] fail_under`
2. `.github/workflows/ci.yaml` → `--cov-fail-under=80`（若有硬編碼）
3. `scripts/pre-push.sh` → 同上

## Risks / Trade-offs

- **[Risk] 補強期間 CI 持續失敗** → Mitigation：先在 PR 環境以 `--cov-fail-under=70` 基線跑，合併時一次升到 80
- **[Risk] Mock 過度深入導致假陽性通過** → Mitigation：每個 unit test 只 mock 一層邊界，驗證行為而非實作細節
- **[Risk] 部分模組業務邏輯複雜難以 unit test** → Mitigation：允許以 `# pragma: no cover` 標記真正無法單元測試的逃生口（如 log-only error branches），但每次使用需 PR 說明理由
- **[Trade-off] omit list 增長** → 接受：router 進入 omit 後從 unit 覆蓋率計算消失，整體覆蓋率數字下降；但因同步要求 integration tests 覆蓋，品質實際不降

## Migration Plan

1. 更新 `pyproject.toml` omit list（6 個 router）→ 重新量測 unit coverage 基線
2. 依 D2 順序逐模組補強 unit tests，每完成一組確認 coverage 上升
3. 所有模組達 ≥ 80% 後，更新 `fail_under = 80` 並同步 CI / pre-push
4. 在本地執行完整套件（unit + integration）驗證無回歸

## Open Questions

（無）— 策略已定，無需額外決策。
