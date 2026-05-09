## Why

富邦帳單系統已遷移為 SPA + API 架構（`fbmbill.taipeifubon.com.tw`），下載流程含**表單圖形驗證碼（captcha）**驗證。現行 `FubonFetcher.fetch_pdf()` 直接拋出 `FetchError("SPA + 尚未實作")`，導致 FUBON 每期 bills=0 / tx=0，是唯一完全阻塞的銀行（見 `docs/e2e-user-guide-walkthrough.md` 問題 #8）。需要一次系統性 research，釐清 captcha 可自動辨識的可行路徑與落地成本，作為後續 `impl-fubon-fetcher-captcha` 類 change 的輸入。

本 change **僅輸出研究結論與落地建議**，不改任何 production code；所有設計決策與測試計畫延後到實作 change。

## What Changes

- 新增 research artifact：記錄富邦 SPA 下載流程的完整 HTTP / DOM trace（登入、表單參數、captcha image endpoint、PDF download endpoint、session / CSRF / cookie 生命週期）
- 比較至少 3 條 captcha 辨識路徑的可行性、準確率與維運成本：
  1. 純影像處理 + Tesseract OCR（傳統 OCR）
  2. 輕量 CNN 模型（自行標注 / 遷移學習）
  3. 第三方付費 captcha API（2captcha / anti-captcha 類）
  以及非 captcha 的 fallback：手動 staging 目錄（`docs/user-guide.md` 既有機制）
- 產出 decision matrix：成功率門檻、每封信成本、法遵風險、首次落地工時、長期維運負擔
- 提出推薦方案與 fallback 策略（例如：主路徑 + 失敗時降級 manual staging）
- **不動**：`ccas.ingestor.fetcher.banks.fubon` 的任何檔案、`FetcherRegistry`、`docs/user-guide.md`（除非 research 發現現行文件有誤）

## Capabilities

### New Capabilities
（無）本 change 為研究性質，不引入新 capability。後續 impl change 會在既有 `fubon-fetcher-impl` spec 上加入 delta。

### Modified Capabilities
（無）research 階段僅記錄調查結論，不修改 spec。

## Impact

- **Affected code**：無（純研究）
- **Affected docs**：在 `openspec/changes/research-fubon-web-fetch-pipeline/` 下輸出 `design.md`（調查方法與 trace）與 `specs/`（空 placeholder，因無 spec 變更）
- **Dependencies**：調查過程可能需要實測 `playwright` / `httpx` / `tesseract` / `opencv-python`，但**不**加入 `pyproject.toml`；任何 POC 腳本放 `/tmp/` 或 `scratch/`，不 commit
- **Downstream**：後續 `impl-fubon-fetcher-captcha`（slug 暫定）change 以本 research 的推薦方案為輸入
- **Risk**：調查樣本僅限使用者自己的 FUBON 郵件，結論可能無法涵蓋所有卡種 / 活動信件；需在 design.md 明確標注樣本範圍
