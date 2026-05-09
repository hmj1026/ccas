## Context

富邦帳單下載系統已遷移為 SPA + REST API + OTP 架構，`FubonFetcher` 目前直接拋錯，導致 FUBON 在 pipeline 中形同停用。完整自動化（playwright + OTP 串接 Telegram bot）風險與成本高，不在本 change 範圍。

選擇：**人工橋接**。使用者自行下載 PDF，放到指定目錄，fetcher 從該目錄「消費」檔案作為 fetch 結果。這樣：
- Pipeline 端不需改 orchestrator
- FUBON ingest→decrypt→parse→classify→notify 全鏈路打通
- SPA 自動化可留給後續 change 無痛接入（manual staging 仍是 fallback）

## Goals / Non-Goals

**Goals:**
- FUBON 使用者可透過手動放檔讓 pipeline 完整跑完。
- Manual staging 檔案被消費後不重複處理（交給既有 ingestor hash 去重）。
- 清晰的使用者指引（user-guide）。
- SPA 自動化路徑保留接入點，後續 change 可替換。

**Non-Goals:**
- 不實作 playwright SPA 流程。
- 不處理 OTP。
- 不碰其他銀行 fetcher。

## Decisions

### D1：Manual staging 目錄由 Settings 控制，不硬編碼

**選擇**：`Settings.fubon_manual_staging_dir: Path = data_dir / "manual-staging" / "FUBON"`，可用 env `FUBON_MANUAL_STAGING_DIR` 覆蓋。

**理由**：遵守 `.claude/rules/python.md` 「所有 config 走 Settings」；使用者可在 Docker 內 mount 別的 host 目錄。

### D2：檔案配對策略 — 帳單月份優先，mtime 備援

**選擇**：從 Gmail message 推導出帳單月份 `YYYY-MM`，在 manual staging 目錄找檔名含該月份的 `.pdf`（例如 `fubon-2026-03.pdf` 或 `202603.pdf`）；若找不到則取最新 mtime 的單一檔案；若有多個且無法區分則 raise。

**理由**：
- 最精準：檔名含月份 → 直接對應
- 其次：mtime 最新假設為「剛下載的那份」
- 明確失敗：避免跑到錯誤的月份

**Alternatives:**
- (A) 只允許精確檔名：使用者命名負擔高
- (B) 第一個檔案：隨 file system 排序結果不穩定

### D3：消費後 move 到正規 staging

**選擇**：manual staging 內的檔案在 fetch 成功後 move 到 `Settings.staging_dir / "FUBON" / <filename>`，與其他銀行一致；manual staging 目錄只當作「入口 tray」。

**理由**：
- 避免 manual staging 目錄累積歷史檔
- 既有 staging 結構沒 special case 需要處理
- 失敗時檔案留在原處，使用者可 retry

### D4：失敗訊息 MUST 含指引

**選擇**：`FetchError.message` 明確包含：
- 指向的 manual staging 目錄絕對路徑
- 建議動作：「請從富邦網銀下載 PDF 並放入該目錄後重試」
- docker 環境下還要提示目錄 host↔container 對應

**理由**：使用者 90% 的失敗情境是忘記放檔，明確 error message 比 silent fail 有價值。

## Risks / Trade-offs

- **[R1]** 使用者放錯月份檔案：fetcher 讀到錯帳單 → 帳單金額與 mail 不符。→ Mitigation：D2 的 filename-first 策略 + 若 parse 後 `billing_month` 與 mail subject 推導不符則 raise（後續 change 可加）
- **[R2]** 多個銀行帳單同時放進 `manual-staging/FUBON/` 會誤用：→ Mitigation：目錄結構 per-bank，FUBON 子目錄只接受 FUBON
- **[R3]** Container 需要 volume mount：使用者忘記 mount 就看不到檔案。→ Mitigation：`docker-compose.yaml` 的 backend `volumes` 已有 `./backend/data:/data`，manual staging 放在 `data/manual-staging/FUBON/` 自動 share

## Migration Plan

1. Settings 加欄位 + `.env.example` 更新
2. `FubonFetcher.fetch_pdf` 改造：try HTML → fallback manual staging → raise
3. Unit test + integration test
4. 更新 user-guide 手動下載步驟
5. 實機驗證：放一份 FUBON PDF 到 `backend/data/manual-staging/FUBON/fubon-2026-03.pdf` → `pipeline --bank FUBON`
6. 無 DB migration

## Open Questions

- **OQ1**：是否同步支援 zip archive 解包？決定：**不做**，只接 `.pdf`。
- **OQ2**：SPA 自動化該做還是不做？決定：**本 change 不做**；後續若需要再開 `add-fubon-spa-automation`。
