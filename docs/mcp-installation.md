# CCAS MCP 安裝與使用

本文件是 CCAS MCP 的安裝 SSOT。CCAS 提供本機 `stdio` MCP server；它只讀取
CCAS 的安全資料投影，不開放寫入工具、不使用網路 transport，也不回傳密碼、OAuth
token、完整卡號或其他 secrets。

## 目前契約

| 項目 | 實作 |
|---|---|
| MCP server | `ccas-mcp`（等同 `python -m ccas.mcp`） |
| Release metadata | v0.8.2；MCP `serverInfo.version` 與 package metadata 同步 |
| Transport | `stdio`；stdout 僅保留 MCP JSON 訊息，診斷訊息走 stderr |
| Tools | `list_bills`、`get_bill`、`query_transactions`、`get_payment_due`、`budget_status`、`pipeline_status` |
| 寫入 | 未提供；`AGENT_WRITE_ENABLED` 不會把目前 server 變成寫入介面 |
| 依賴 | Python 3.12+、uv；`backend/pyproject.toml` 宣告 `mcp>=2.2.0,<3` |
| 時間欄位 | Agent DTO 的 datetime 以 UTC RFC3339 `Z` suffix 輸出；既有 SQLite naive value 視為 UTC |

需要了解資料欄位與安全邊界時，先讀 [`current-implementation.md`](CODEMAPS/current-implementation.md)
與 [`0001-agent-notion-trust-boundary.md`](adr/0001-agent-notion-trust-boundary.md)。

## 方式 A：人員手動安裝（本機開發）

若 MCP client 所在主機不使用 Docker，先讀
[`無 Docker 的 Agent Host`](non-docker-agent-host.md)。該文件列出 MCP-only 的最小
依賴、資料庫準備、`get_payment_due` smoke check，以及 worker/scheduler 才需要的
Redis host service。

1. 取得程式碼並安裝 backend 依賴：

   ```bash
   git clone https://github.com/hmj1026/ccas.git
   cd ccas/backend
   uv sync
   cp ../.env.example ../.env
   export API_TOKEN="$(openssl rand -hex 32)"
   ```

   直接以 `uv` 啟動時，`API_TOKEN` 必須存在於環境或 `.env`；Docker entrypoint
   才會在未設定時自動產生 token。上述 token 僅供本機啟動檢查，請勿貼到對話或提交。

2. 確認 server 可以啟動。這是長駐的 stdio 程序，啟動後不會顯示互動提示；按
   `Ctrl-C` 結束：

   ```bash
   uv run ccas-mcp
   ```

3. 將 MCP client 的 server command 設為下列形式，並把路徑換成絕對路徑：

   ```json
   {
     "mcpServers": {
       "ccas": {
         "command": "uv",
         "args": ["run", "--directory", "/absolute/path/to/ccas/backend", "ccas-mcp"]
       }
     }
   }
   ```

   MCP client 應直接啟動這個 command，不要把 stdout 導向 log 或加入 shell echo。
   若 client 不支援 `--directory`，改用 `cwd=/absolute/path/to/ccas/backend`，command
   為 `uv run ccas-mcp`。

4. 驗證：在 MCP client 中列出 tools，應看到上述六個名稱；再依序等待 response 後呼叫
   `get_payment_due`、`pipeline_status` 或 `list_bills`。Agent datetime 欄位應使用
   `Z` suffix。若沒有資料，先依
   [`install-quickstart.md`](install-quickstart.md) 啟動 CCAS 並完成登入。

## 方式 B：委託 AI 安裝

可將下列委託內容貼給具備本機 terminal 與 MCP 設定權限的 AI coding agent：

> 請在 `/absolute/path/to/ccas` 安裝 CCAS MCP。先讀 `docs/mcp-installation.md`、
> `backend/pyproject.toml` 與 `.mcp.json`，確認不要修改 secrets、不要啟用網路
> transport、不要新增寫入工具。執行 `cd backend && uv sync`，以
> `uv run ccas-mcp` 做啟動檢查，然後依我指定的 MCP client 寫入其使用者設定。
> 設定完成後列出實際修改的檔案、啟動 command、六個 tools，以及測試結果；若缺少
> 權限或 client 名稱，停在可恢復的步驟並提出一個明確問題。

AI 執行時必須遵守：

- 先確認目標 client（Claude Desktop、Codex、Gemini CLI 或其他）與設定檔位置，再寫入設定。
- 使用絕對 repository path；不要建立跨 repository symlink，也不要把 `.env`、token、credentials
  或 MCP 設定中的秘密貼到對話或 commit。
- 設定前備份既有 client config；只新增 `mcpServers.ccas`，保留其他 server。
- 安裝後執行一次 `uv run ccas-mcp` 啟動檢查與 client 的 tool discovery；失敗時保留錯誤
  輸出（遮罩秘密）並停止，不要反覆重試或刪除使用者設定。

若 AI 沒有本機寫檔或執行權限，請改用方式 A；AI 只能產生設定片段，不能代替使用者
在 GUI 中授權或輸入秘密。

## 專案內 GitNexus MCP

本 repository 的 [`.mcp.json`](../.mcp.json) 已提供 GitNexus server，供代理進行程式碼
探索與 impact analysis。它與 CCAS 業務 MCP 是兩個不同 server：

- `gitnexus`：程式碼知識圖譜，command 為 `npx -y gitnexus@1.6.3 mcp`。
- `ccas`：業務資料唯讀查詢，command 為上方的 `uv run ... ccas-mcp`。

不要以其中一個取代另一個，也不要把任何一個 server 改成遠端 HTTP endpoint；若要
規劃遠端連線，必須先新增安全與授權設計文件。

## 排錯

### 升級後 MCP 子行程殘留

MCP server 由 Agent host 建立 stdio 子行程，不由 `host-services.sh` 管理。
`Restart`／`Add` 之後 host 可能仍顯示 connected，但實際連到升級前啟動的
`ccas-mcp` 或 logging wrapper。此時 `pipeline_status` 仍可能回舊的
`-32602 date-time`，即使 checkout 已是 v0.8.2+。

單靠 Restart **不能**保證載入新碼。每次 CCAS 升級後、或懷疑 session 殘留時，固定：

1. 若本次有升 CCAS 且使用 host services，先重裝並 smoke，見
   [`non-docker-host-services.md`](non-docker-host-services.md)。
2. 確認殘留行程：

   ```bash
   pgrep -af 'ccas-mcp-logging-wrapper|ccas-mcp'
   ```

3. 停掉該機所有 CCAS MCP stdio（會中斷目前所有 `ccas-mcp` session）：

   ```bash
   pkill -f 'ccas-mcp-logging-wrapper|ccas-mcp' || true
   ```

4. 在 host 端 Restart 或重新 Add MCP server。command 維持：

   ```text
   uv run --directory /absolute/path/to/ccas/backend ccas-mcp
   ```

5. 依序等待 response：`tools/list` → `get_payment_due` → `pipeline_status`。
   `pipeline_status` 的 timestamp 須帶 UTC `Z`。

區分兩種失敗：

- `tools/call` 在數毫秒內失敗，且 server／wrapper log **沒有**對應 JSON-RPC
  request：host stale session 或 routing，見下一節。
- server wire log **有** `tools/call` 與 response，但 host 回 `-32602` 並指出
  `date-time`：舊行程或未升級的 DTO，見「date-time validation」一節。

### stdio session 顯示 connected 但 tools/call 顯示 `Not connected`

若 client 顯示 server 已 connected 且能列出 6 個 tools，但呼叫在數毫秒內回報
`Not connected`，而 server／wrapper log 沒有收到對應 JSON-RPC `tools/call`，這是
host 的 stale session 或 routing lifecycle 症狀，不是 CCAS query handler 的資料錯誤。

請先做上一節的 PID 回收，再於 host 端：

1. 移除或停止目前的 `ccas` MCP entry。
2. 重新 Add／Restart MCP server，讓 host 建立新的 stdio session。
3. 重新執行 `tools/list`，再逐次等待 response 呼叫 `get_payment_due`。

若新 session 的 server wire log 已收到 `tools/call` 且回傳 result，請將 host connector
的原始錯誤提交給該 host 的維護者；CCAS 端不需以 Redis、API 或 supervisord 解法處理
這個 pre-roundtrip failure。

### `pipeline_status` 顯示 `-32602` 與 `date-time` validation

這表示 host 已收到 server response，但嚴格驗證 structured output 時拒絕沒有 timezone
offset 的 datetime。v0.8.2 會把 Agent datetime 統一輸出為 UTC `Z`，不需要資料庫
migration。若 checkout 已是 v0.8.2+ 仍出現此錯，幾乎都是舊 MCP 子行程，請走
「升級後 MCP 子行程殘留」而不是只 Restart。

### timeout smoke test 與實際 tool call

`timeout 3 uv run ccas-mcp` 只確認長駐程序可以啟動，不會驗證 `tools/call`。若一次把
多個 JSON-RPC request 寫入 stdin 後立即關閉 stdin，server 可能在 pending request
完成前收到 EOF，產生 `Connection closed`；完整驗證必須逐次寫入 request、等待 response，
並保持 stdin 開啟直到最後一個 response 收到。

| 症狀 | 檢查 |
|---|---|
| `uv: command not found` | 安裝 uv，或改用已安裝的 Python/venv；不要直接使用系統 Python 猜測依賴。 |
| 找不到 `ccas-mcp` | 確認 command 的 `--directory` 指向 `ccas/backend`，並重新執行 `uv sync`。 |
| client 顯示 JSON parse error | 確認 server 使用 stdio，stdout 沒有 shell banner、debug print 或 log。 |
| Restart 後仍跑舊碼或 `date-time` 錯 | 殺殘留 PID 再重接；見「升級後 MCP 子行程殘留」。 |
| tools 存在但查不到資料 | 啟動 CCAS backend、確認 data path 與登入狀態，再呼叫 `pipeline_status`。 |
| 需要寫入或同步 Notion | 目前契約不支援；遵守 ADR 的信任邊界，另行提出變更與授權設計。 |
