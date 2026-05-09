# Design: fix-fubon-fetcher-spa-migration

## Context

FUBON 帳單下載系統在某個時間點從 server-rendered HTML form + CAPTCHA 改版為 Vue SPA + axios API + 可能的 OTP 驗證。現有 `FubonFetcher` 針對舊系統設計，在新系統下三層失效（keyword、domain、flow）。

本次的目標不是完整追上新系統（那需要反向工程 SPA bundle、處理 OTP 簡訊等，工作量大且可能無法完全自動化），而是：

1. **讓 pipeline 正確路由 FUBON 郵件** — 不再靜默略過
2. **提供明確錯誤訊息** — 使用者能在 JSON summary 看到「SPA 未支援」
3. **保留未來升級的擴充點** — `can_fetch` 與 domain 白名單修正後，只需替換 `fetch_pdf` 實作即可

## Stakeholders

- **使用者（Paul）**：需要看到 FUBON 的真實狀態（非靜默 0），並能決策是否投入反向工程成本
- **後續 FUBON SPA 實作者**：本變更留下清楚的狀態錯誤訊息與 regression test fixture，做為後續實作的起點

## Decisions

### Decision 1: `can_fetch` 從「關鍵字匹配」改為「網域匹配」

**選項**：
- (a) 改為匹配 `<img alt="下載本期帳單(PDF)">`（新關鍵字）
- (b) 改為匹配「錨點 href 指向 `fbmbill.taipeifubon.com.tw`」
- (c) 兩者擇一或同時

**決定**：採 (b) — 網域匹配

**理由**：
- 網域比按鈕圖片 alt text 更穩定（圖片 alt 可能隨 UI 改版變動）
- 未來若富邦再改版按鈕文字但維持同一網域，`can_fetch` 不需修正
- 若想防呆，可同時檢查網域在 `_ALLOWED_DOMAINS` 內（SSOT，與 `_validate_url` 一致）

**實作**：
```python
def can_fetch(self, html_body: str) -> bool:
    if not html_body:
        return False
    try:
        soup = BeautifulSoup(html_body, "html.parser")
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            parsed = urlparse(href)
            if parsed.hostname in _ALLOWED_DOMAINS:
                return True
        return False
    except Exception:
        logger.debug("FUBON can_fetch HTML 解析失敗", exc_info=True)
        return False
```

### Decision 2: `fetch_pdf` 顯式 `FetchError` 而非 `NotImplementedError`

**選項**：
- (a) `raise NotImplementedError(...)` — Python 慣例
- (b) `raise FetchError("FUBON", "...")` — 沿用既有錯誤體系

**決定**：採 (b)

**理由**：
- `NotImplementedError` 會讓 `_process_web_fetch` 捕捉為 `Exception` 並降級為通用錯誤，失去 bank_code 上下文
- `FetchError` 已被 `ingestor/job.py` 的錯誤處理流程正確分類、記錄到 JSON summary 與 logs
- 使用者看 summary 時能直接看到「FUBON fetch 失敗 + 原因」，一致性更好

### Decision 3: 加入 `fbmbill.taipeifubon.com.tw` 到 `_ALLOWED_DOMAINS`

**考量**：網域白名單的目的是防止憑證外洩攻擊（惡意郵件偽造連結）。加入新網域會放寬防護邊界。

**決定**：加入，但在 code 與 spec 註明該網域為 FUBON 官方帳單下載服務。

**理由**：
- 網域仍是 `*.taipeifubon.com.tw` 根網域，屬官方資產
- 未加入會導致 `can_fetch` 回傳 True 但 `_extract_download_url` 立即爆 `FetchError` — 與 Decision 1 不一致
- 為了未來反向工程 SPA API 也必須允許此網域

### Decision 4: 不重寫單元測試整個檔案，只增補

測試檔案保留原 CAPTCHA flow 測試（標記為 `@pytest.mark.skip(reason="FUBON SPA 遷移後不再走 CAPTCHA 流程")`）而非刪除，以保留 git 歷史可見性，並在未來決定重寫時方便對照舊行為。

## Risks

| 風險 | 緩解 |
|------|------|
| 未來 FUBON 再次改版，`fbmbill.taipeifubon.com.tw` 網域變更 | 網域在 `_ALLOWED_DOMAINS` 是 const，需主動維護；記錄於變更 archive 讓歷史可查 |
| 使用者誤以為 FUBON 已可自動下載 | `fetch_pdf` 錯誤訊息明確寫「尚未實作」；README 可加註 |
| 惡意郵件偽造 fbmbill 網域連結誘發 credential 外洩 | `fetch_pdf` 目前拋錯不發任何 request，零風險；未來實作時再由 reviewer 檢視 |

## Alternatives Considered

### Alt A: 完整重寫 FubonFetcher 追上 SPA 流程
拒絕理由：OTP 可能完全阻擋自動化；反向工程 SPA bundle 需要數小時；本次任務的核心目標（7 銀行端到端驗證）不應被 FUBON 單點阻塞。

### Alt B: 完全刪除 FubonFetcher + 將 FUBON 從 banks registry 移除
拒絕理由：其他元件（parser、classify、notify）都正常，只有 fetch 失效。刪除會連帶影響未來重新啟用時的成本。

### Alt C: 對 FUBON 郵件直接在 `_process_web_fetch` skip
拒絕理由：靜默略過正是當前問題。顯式失敗更誠實、更可觀測。
