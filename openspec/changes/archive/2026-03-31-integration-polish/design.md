## 背景 (Context)

CCAS 已完成所有功能 change 的規格定義（gmail-ingestor、parser-engine、keyword-classifier、telegram-bot、frontend-dashboard），各模組均有各自的單元測試與整合測試。然而目前缺少三個跨模組基礎：

1. **端對端測試**：沒有任何一個測試覆蓋從 Gmail 抓取到 Telegram 通知的完整流程，無法確認各模組接縫正確。
2. **統一例外階層**：各模組各自拋出不同例外型別，跨模組錯誤傳遞難以區分來源，也無法統一格式化錯誤訊息。
3. **結構化日誌**：目前各處可能混用 `print()` 與不一致的 `logging` 設定，缺乏 JSON 格式、log level 集中控制，以及機敏資訊遮罩。

此 change 是整個開發計畫的最終收尾，屬於跨切面（cross-cutting）變更，影響測試、基礎模組與所有既有模組。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 建立端對端測試套件，以 mocked Gmail/Telegram、真實 SQLite 資料庫與真實 pipeline 流程驗證完整路徑
- 定義 `CcasError` 基底例外與各模組子類別，統一跨模組錯誤格式
- 建立 JSON 格式結構化日誌，配合模組層級 logger 與機敏資訊遮罩過濾器
- 補齊 staging 狀態機生命週期測試，含成功路徑與錯誤分支
- 新增整合驗證清單（所有模組可匯入、migration 可套用、測試覆蓋率 >= 80%）

**非目標：**
- 不建立 CI/CD 流水線或部署自動化
- 不執行負載測試或效能基準測試
- 不引入 structlog 或其他第三方日誌框架
- 不修改任何既有模組的商業邏輯

## 決策 (Decisions)

### D1: E2E 測試使用 mocked 外部服務 + 真實資料庫

**選擇**: E2E 測試 mock Gmail API 與 Telegram API，但使用真實的 in-memory SQLite 資料庫（WAL 模式）與真實的 pipeline 執行路徑（不 mock 內部模組）。

**理由**: Mock 外部服務可讓 E2E 測試在無網路環境下穩定執行，且不需要真實帳號憑證。使用真實資料庫而非 mock 可確保 migration、ORM 映射與狀態轉換邏輯均被真實驗證。使用真實 pipeline 流程而非 mock 內部模組，才能捕捉接縫問題。

**考慮過的替代方案**:
- 完全 mock 所有依賴（包含 DB）：可以更快，但無法驗證跨模組接縫與真實資料流
- 使用真實 Gmail 帳號測試：在 CI 環境中不穩定，且管理憑證成本高

### D2: 結構化日誌採用 Python stdlib `logging`，JSON 自訂 Formatter

**選擇**: 使用 Python 標準函式庫 `logging` 模組搭配自訂 `JsonFormatter`，輸出 JSON 格式日誌。每個模組使用 `logging.getLogger(__name__)` 取得模組層級 logger。

**理由**: stdlib `logging` 已內建在 Python 中，不增加任何相依套件。`__name__` 作為 logger 名稱可提供精確的模組來源定位，且與 `logging.config` 的階層式設定相容。JSON 格式方便後續接入 log aggregation 工具（如 Loki、Datadog）。

**考慮過的替代方案**:
- structlog：功能豐富但引入額外相依，對本專案規模過重
- loguru：API 友善但同樣是第三方套件，與 CCAS 保持最小相依的原則衝突

### D3: 機敏資訊遮罩採用 `logging.Filter` 子類別

**選擇**: 實作 `RedactingFilter(logging.Filter)` 過濾器，在日誌記錄輸出前掃描訊息內容，將符合機敏模式的欄位值替換為 `[REDACTED]`。遮罩規則涵蓋 OAuth token、密碼、credentials 路徑。

**理由**: `logging.Filter` 是 stdlib 提供的標準擴充點，可在 handler 層級掛載，不需修改所有呼叫端的 log 語句。集中管理遮罩規則比在每個 `logger.info()` 呼叫端手動遮罩更不容易漏網。

**考慮過的替代方案**:
- 在每個 log 呼叫端手動遮罩：容易遺漏，維護成本高
- 完全不記錄包含機敏資訊的欄位：會損失過多診斷資訊，難以排查 OAuth 問題

### D4: Staging 狀態機生命週期以明確測試案例驗證

**選擇**: E2E 測試中明確斷言以下狀態轉換序列：成功路徑 `staged -> decrypted -> parsed`；錯誤分支 `staged -> decrypt_failed`、`staged -> parse_failed`。每個狀態轉換都有獨立的測試案例，不合併在同一個 test function 中。

**理由**: 狀態機是後續 dashboard 顯示與人工補救流程的核心依賴，若狀態轉換有誤，會在多個下游功能中同時造成問題。獨立測試案例也讓失敗定位更精準。

**考慮過的替代方案**:
- 只測試成功路徑：無法驗證錯誤分支的狀態是否正確落地
- 在單一 test function 中測試所有狀態：失敗時難以定位是哪個轉換出錯

### D5: 共用例外階層以 `CcasError` 為基底，各模組繼承子類別

**選擇**: 在 `core/exceptions.py` 定義 `CcasError(Exception)` 基底類別，各模組分別繼承 `IngestError`、`DecryptError`、`ParseError`、`ClassifyError`、`NotifyError`。所有例外均攜帶統一的 `message` 與可選的 `context` 欄位。

**理由**: 統一的例外階層讓呼叫端可以選擇捕捉特定模組例外（精確處理）或捕捉 `CcasError`（統一降級處理），不需針對每個模組撰寫不同的 except 子句。`context` 欄位提供結構化的診斷資訊，方便日誌格式化。

**考慮過的替代方案**:
- 各模組各自定義獨立例外，不共用基底：跨模組捕捉困難，錯誤格式不一致
- 全部使用 Python 內建例外型別（`ValueError`、`RuntimeError`）：語義不明確，難以區分來源

## 風險 / 取捨 (Risks / Trade-offs)

**E2E 測試啟動成本較高** → 需要初始化完整 DB schema 與多個 mocked 服務，測試套件啟動時間會比單元測試長；以 pytest fixture scope 共用 DB 設定降低影響

**機敏遮罩規則難以涵蓋所有情境** → `RedactingFilter` 只能遮罩已知模式；開發者仍需避免在 log 語句中直接嵌入完整憑證物件，需在 code review 中持續把關

**跨模組例外改動影響所有既有模組** → 引入 `CcasError` 階層需要各模組的小量修改；此 change 為最終收尾，接受短暫的跨模組改動

**狀態機驗證依賴各模組實作正確** → E2E 測試的價值在於找出接縫問題；若測試失敗，需先確認是測試設計問題還是實作問題，避免為了讓測試通過而調整斷言
