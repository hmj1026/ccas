# E2E User Guide Walkthrough — 全銀行真實資料走查

本文件對應 `docs/user-guide.md` 的完整 pipeline，用來逐銀行、逐階段驗證「Gmail → 前端看到資料」這條線。

- **執行環境**：Docker compose 完整堆疊
- **資料來源**：真實 Gmail + 真實 PDF（`.env` 內的 `PDF_PASSWORD_<BANK>`）
- **問題處理**：每發現一個問題立即 `/opsx:new` 開 change，不批次合併
- **詳細 SOP**：見 `~/.claude/plans/groovy-yawning-avalanche.md`

---

## Stage 0：環境 Pre-flight（只做一次）

- [ ] `.env` 齊全：`./scripts/check-env.sh` 無錯誤
- [ ] `PDF_PASSWORD_CTBC` / `_SINOPAC` / `_ESUN` / `_UBOT` / `_CATHAY` / `_TAISHIN` / `_FUBON` 全部填好
- [ ] `credentials.json`、`token.json` 位於 `.env` 指定路徑
- [ ] `docker compose up -d` 6 個服務（backend / worker / scheduler / bot / frontend / redis）全部 healthy（SQLite 為 file-based，無獨立 container）
- [ ] `curl http://localhost:8000/health` → 200
- [ ] `http://localhost:8080` 能用 `API_TOKEN` 登入

---

## Per-Bank Checklist

每家銀行跑 Stage 1~7。發現問題 → 在「問題追蹤表」加一列 → `/opsx:new` → 修完再打勾。

CLI 範本（把 `<BANK>` 換成 `CTBC` / `SINOPAC` / `ESUN` / `UBOT` / `CATHAY` / `TAISHIN` / `FUBON`）：

```bash
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank <BANK> --to ingest
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank <BANK> --from decrypt --to decrypt
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank <BANK> --from parse --to parse
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank <BANK> --from classify --to classify
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank <BANK> --from notify --to notify
```

### CTBC — 中國信託
- [ ] **S1 ingest**：信件 count > 0、落盤到 `STAGING_DIR`
- [ ] **S1 dedup**：重跑一次 `skipped=N, new=0`
- [ ] **S2 decrypt**：PDF 可讀
- [ ] **S3 parse**：`parsed_rows > 0`、金額/日期/ROC 年份對得上 PDF
- [ ] **S4 classify**：DB category 非 null / 非 `unknown`
- [ ] **S5 notify**：Telegram 收到摘要（可選）
- [ ] **S6 API**：`GET /api/bills?bank=CTBC` 有本期 bill
- [ ] **S6 API**：`GET /api/transactions?bank=CTBC` 數量與 parse 一致
- [ ] **S6 API**：`GET /api/bills/{id}/download` 能下載原 PDF
- [ ] **S7 前端 /overview**：CTBC 卡片顯示最新金額
- [ ] **S7 前端 /bills**：列表有 row、detail 看得到細項
- [ ] **S7 前端 /transactions**：過濾 CTBC 有資料、金額一致
- [ ] **S7 前端 /analytics**：圖表包含 CTBC 貢獻

### SINOPAC — 永豐
- [ ] S1 ingest / dedup
- [ ] S2 decrypt
- [ ] S3 parse
- [ ] S4 classify
- [ ] S5 notify（可選）
- [ ] S6 API：bills / transactions / download
- [ ] S7 前端：overview / bills / transactions / analytics

### ESUN — 玉山
- [ ] S1 ingest / dedup
- [ ] S2 decrypt
- [ ] S3 parse
- [ ] S4 classify
- [ ] S5 notify（可選）
- [ ] S6 API：bills / transactions / download
- [ ] S7 前端：overview / bills / transactions / analytics

### UBOT — 聯邦
- [ ] S1 ingest / dedup
- [ ] S2 decrypt
- [ ] S3 parse
- [ ] S4 classify
- [ ] S5 notify（可選）
- [ ] S6 API：bills / transactions / download
- [ ] S7 前端：overview / bills / transactions / analytics

### CATHAY — 國泰
- [ ] S1 ingest / dedup
- [ ] S2 decrypt
- [ ] S3 parse
- [ ] S4 classify
- [ ] S5 notify（可選）
- [ ] S6 API：bills / transactions / download
- [ ] S7 前端：overview / bills / transactions / analytics

### TAISHIN — 台新
- [ ] S1 ingest / dedup
- [ ] S2 decrypt
- [ ] S3 parse
- [ ] S4 classify
- [ ] S5 notify（可選）
- [ ] S6 API：bills / transactions / download
- [ ] S7 前端：overview / bills / transactions / analytics

### FUBON — 台北富邦
- [ ] S1 ingest / dedup
- [ ] S2 decrypt
- [ ] S3 parse
- [ ] S4 classify
- [ ] S5 notify（可選）
- [ ] S6 API：bills / transactions / download
- [ ] S7 前端：overview / bills / transactions / analytics

---

## Stage 8：收尾

- [ ] 上方 7 銀行 × Stage 1~7 全部 `[x]`
- [ ] 問題追蹤表所有列狀態為 `archived`
- [ ] `docker compose down`
- [ ] 記錄本次總用時：`______`

---

## 問題追蹤表

發現問題時加一列；修完把狀態改成 `archived` 並回到上方打勾。

| # | 銀行 | 階段 | 症狀 | 對應 change slug | 狀態 |
|---|------|------|------|------------------|------|
| 1 | ALL | S0 pre-flight | docker compose 跑 pipeline 前未 seed `bank_configs`；container 亦未 mount `config/`，導致 `ingest` 回報「未找到任何啟用的銀行設定」。user-guide 沒寫要手動跑 setup.sh。workaround：把 yaml 複製到 `backend/data/` 後用 `--config /data/... --registry /data/...` 執行 `bank_configs --apply`。 | fix-docker-bank-configs-seed | archived |
| 2 | CTBC | S3 parse | 中文字元損毀：`統一超商`→`一統一超商 斷體/四體`；`MITSUI OUTLET 台中港`→`MITSUI 全中港一`；`統一時代百貨`→`統一時代百鋼`。疑似 PDF CJK 字型對照錯誤（CID→Unicode）或 parser text extraction 問題。樣本 911 筆皆有類似現象。 | fix-ctbc-parser-cjk-corruption | archived |
| 3 | ALL | S4 classify | 全銀行 3348 筆交易全數為 `未分類`（CTBC 911 / SINOPAC 1464 / ESUN 280 / UBOT 381 / CATHAY 90 / TAISHIN 222）。classify stage 回報 classified 數與該銀行 tx 一致但 DB category 全部為預設值。需釐清：(a) 規則表是否為空 (b) 是否因 #2 / 全形字元 / 卡別前綴導致 keyword 無法匹配 (c) `classified` 計數語意是否為「處理數」而非「命中規則數」。根因：`categories` 表為空且無 seed 機制。 | fix-classify-rules-not-matching | archived |
| 4 | SINOPAC | S3 parse | 還款/自扣條目未過濾：如 `永豐自扣已入帳，謝謝！` amount=-16652 被當成一般交易；亦發現「悠遊卡自動加值」「A- / MF- 卡別前綴」等格式，可能影響後續 classify 與 analytics 匯總。 | fix-sinopac-parser-filter-refunds | archived |
| 5 | UBOT | S3 parse | 回饋/還款條目混入交易：`刷卡現金回饋－吉鶴卡日幣回饋` amount=-3、`專案：想分調整全球人壽` amount=-12152 等負值被視為一般交易。行為與 #4 類似，可能需要統一 parser 過濾策略。 | fix-ubot-parser-filter-cashback | archived |
| 6 | CATHAY | S3 parse | 嚴重：107 張 bills 只抓到 90 筆 transaction（平均 <1 tx/bill），且抓到的都是「帳單分期 XX-12 33,293 ...」這類分期說明列，實際消費明細完全沒被捕捉。疑似 parser 把「分期明細表」誤判為交易表，或 row regex 對錯資料區塊。 | fix-cathay-parser-capture-transactions | archived |
| 7 | TAISHIN | S2 decrypt | 部分歷史帳單 decrypt 失敗：`Invalid password`（樣本：`TSB_Creditcard_Estatement_2020{01..10}.pdf`）。最近帳單 decrypt 成功（bills=16 / tx=222）。疑似 TAISHIN 舊版 PDF 密碼格式與現行 `PDF_PASSWORD_TAISHIN` 不同。 | fix-taishin-parser-historical-password | archived |
| 8 | FUBON | S1 ingest | **結案**：SPA 遷移 + schema drift + JWT redaction 已修。自動化 fallback 至 manual-staging 目錄（使用者手動下載 PDF），pipeline 全鏈路可通。SPA 完整自動化留後續 change。 | fix-fubon-fetcher-spa-migration-completion | archived |
| 9 | FUBON | S1 ingest | **Captcha solver 持續解錯**：實跑 33 筆中 ~10 筆以 `captcha_retry_exhausted: 7 attempts failed` 告終。EasyOCR 實測命中率低於 research 預估的 ~30%×7=91.8% 覆蓋率。改用 captcha-specialized `ddddocr`（ONNX CNN）取代 EasyOCR+torch；baseline 9/10=90% FP=0；實跑 0 次 `captcha_retry_exhausted`；image size 1.82 GB → 911 MB。 | fix-fubon-captcha-solver-accuracy | archived |
| 10 | FUBON | S1 ingest | **errorMsg 分類缺類別**：FUBON 對失效 / 查無帳單的 serial_key 回 `登入失敗, 查無資料`，未命中 `_classify_error_msg` 的 `驗證碼/身分證/出生` keyword → 收斂成 `unknown` → flow 誤翻成 `credentials_wrong`。實跑 33 筆中 ~20 筆命中。已於 `_classify_error_msg` 新增 `record_not_found` slug（比對 `查無資料/查無此筆`），flow 迴圈遇此 slug 直接 raise 不重試、不誤報帳密錯。 | codex-adversarial-review-fix | archived |
| 11 | FUBON | S3 parse | **Parser can_parse=False**：舊 staging dir 的 FUBON PDF 被帶進 parse stage，新版 `FUBONParserV1.can_parse()` 全部拒收。可能是舊 PDF 版型與新 parser mismatch，或 staging 未被清。需另案調查。 | TBD | open |
| 12 | ALL | S5 notify | 所有銀行 `notify sent=0`，非失敗。原因待查：TELEGRAM_CHAT_ID 未設定或為空時 notify 靜默跳過。需確認是否為預期行為（user-guide 有提到 chat_id 留空則不送）。低優先。 | N/A（預期行為） | skip |
| 13 | ALL | S7 前端 | 前端靜態站 `http://localhost:8080/` 回 200，但視覺 smoke（/overview, /bills, /transactions, /analytics 是否正確 render）本次未以 browser 驗證。需使用者手動登入確認。 | TBD | manual |

狀態欄值：`open` / `spec-ready` / `in-progress` / `applied` / `archived`

> `spec-ready` = openspec change 的 proposal/design/specs/tasks 已建立並 `openspec validate` 通過，尚未進入 TDD 實作階段。

### 新增問題 SOP

1. 這張表加一列，`change slug` 先填 `TBD`
2. 執行 `/opsx:new`，slug 建議 `YYYY-MM-DD-fix-<bank>-<stage>-<short>`（對齊 `openspec/changes/archive/` 既有命名）
3. **先建 `tasks.md`**（見 `.claude/rules/execution-policy.md`，禁止先寫 code）
4. 回填本表 `對應 change slug`
5. `tdd-guide` → 實作 → `python-reviewer`（若動 SQL 加 `database-reviewer`）
6. `/opsx:apply` → `/opsx:verify` → `/opsx:archive`
7. 把狀態改成 `archived`，回到上方該 stage 打勾
8. 繼續下一個 stage 或下一家銀行

### 例外：跨銀行共同根因

若 2+ 家銀行同一 stage 失敗且 root cause 相同（orchestrator / registry / API schema），允許合併為單一 change，但 `proposal.md` 要列出所有受影響銀行，且本表每家都加一列並指向同一個 slug。
