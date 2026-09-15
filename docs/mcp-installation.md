# CCAS MCP 安裝與使用

本文件是 CCAS MCP 的安裝 SSOT。CCAS 提供兩個本機 adapter，共用
`create_server()` 與同一組六個唯讀工具：

1. **loopback Streamable HTTP**（Grok／Cursor 家族 host 首選）：常駐行程聽
   `http://127.0.0.1:8001/mcp`。
2. **stdio**（仍由 host spawn 子行程的 client 後援）：`ccas-mcp`／
   `python -m ccas.mcp`。

兩者只讀取 CCAS 的安全資料投影，不開放寫入工具，也不回傳密碼、OAuth token、
完整卡號或其他 secrets。HTTP 只聽 loopback，**不是**遠端公開 MCP。Streamable HTTP
的 GET 可能用 SSE framing 推事件，那是現行 spec 的一部分，**不是**已 deprecated
的 HTTP+SSE（獨立 `/sse` + `/messages`）；本實作不掛後者。

## 目前契約

| 項目 | 實作 |
|---|---|
| stdio server | `ccas-mcp`（等同 `python -m ccas.mcp`） |
| HTTP server | `ccas-mcp-http`（等同 `python -m ccas.mcp.http`） |
| HTTP 入口 | `http://127.0.0.1:8001/mcp`（port 由 `MCP_HTTP_PORT` 覆寫） |
| HTTP bind | 預設 `MCP_HTTP_HOST=127.0.0.1`；非 loopback 在 `create_http_app()` fail-closed，不是 Settings validator（誤設 `0.0.0.0` 不得讓 worker／API 起不來） |
| HTTP 認證 | `Authorization: Bearer`，token 與 REST 的 `API_TOKEN`／`current_api_token()` 相同；**不接受** REST session cookie |
| 常駐 | supervisord capability `mcp-http`（比照 `api`）。systemd／launchd **不支援** |
| Release metadata | 與 `backend/src/ccas/__init__.py` 的 package metadata 同步；目前為 v0.9.0 |
| Transport | stdio（stdout 僅 MCP JSON）或官方 SDK Streamable HTTP；禁止 deprecated HTTP+SSE |
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
Redis host service。`install mcp-http` **不需要** Redis。

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
   HTTP MCP 用同一個 token 當 Bearer；git 範例只寫 `${env:API_TOKEN}` 插值。

### 首選：loopback Streamable HTTP（Grok／Cursor 家族）

2. 常駐 HTTP adapter。supervisord 是唯一支援 `mcp-http` 的 driver（與 `api` 相同）；
   systemd／launchd 會在選此 target 時失敗：

   ```bash
   cd /absolute/path/to/ccas
   cd backend && uv sync --frozen --extra supervisor && cd ..
   ./scripts/host-services.sh --driver=supervisord install mcp-http
   ./scripts/host-services.sh --driver=supervisord smoke mcp-http
   ```

   `install all` 在 supervisord 下也會一併安裝 `mcp-http`。Runner 實際執行：

   ```text
   uvicorn ccas.mcp.http:create_http_app --factory --host 127.0.0.1 --port <mcp_http_port>
   ```

   不要用 systemd／launchd 跑 MCP HTTP。前景檢查（不經 host-services）可用：

   ```bash
   uv run --directory /absolute/path/to/ccas/backend ccas-mcp-http
   # 或：uv run --directory /absolute/path/to/ccas/backend python -m ccas.mcp.http
   ```

   smoke 預期：對 `/mcp` **不帶** Bearer 得到 HTTP **401**。

   ```bash
   curl -s -o /dev/null -w '%{http_code}' \
     -H 'Accept: application/json, text/event-stream' \
     http://127.0.0.1:8001/mcp
   ```

3. 將 MCP client 設為 URL，不要把真實 token 寫進 git 或對話。Cursor／Grok 家族
   常見片段（把插值交給 host；本機 `.env` 已有 `API_TOKEN`）：

   ```json
   {
     "mcpServers": {
       "ccas": {
         "url": "http://127.0.0.1:8001/mcp",
         "headers": {
           "Authorization": "Bearer ${env:API_TOKEN}"
         }
       }
     }
   }
   ```

   若該 host 需要顯式 transport 型別，加上 `"type": "streamable-http"`（其餘欄位相同）。
   不要填 `0.0.0.0`、不要用遠端 URL、不要改掛 deprecated `/sse`。

4. 驗證：在 MCP client 中列出 tools，應看到上述六個名稱；再依序等待 response 後呼叫
   `get_payment_due`、`pipeline_status` 或 `list_bills`。Agent datetime 欄位應使用
   `Z` suffix。若沒有資料，先依
   [`install-quickstart.md`](install-quickstart.md) 啟動 CCAS 並完成登入。

### 後援：stdio（host 仍 spawn 子行程時）

若 client 不能連 loopback URL，才改用 stdio。確認 server 可以啟動。這是長駐的
stdio 程序，啟動後不會顯示互動提示；按 `Ctrl-C` 結束：

```bash
   uv run --directory /absolute/path/to/ccas/backend ccas-mcp
```

將 MCP client 的 server command 設為下列形式，並把路徑換成絕對路徑：

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
為 `uv run ccas-mcp`。stdio 不要求 Bearer。

## 方式 B：委託 AI 安裝

可將下列委託內容貼給具備本機 terminal 與 MCP 設定權限的 AI coding agent：

> 請在 `/absolute/path/to/ccas` 安裝 CCAS MCP。先讀 `docs/mcp-installation.md`、
> `backend/pyproject.toml` 與 `.mcp.json`。Grok／Cursor 家族 host 請用 loopback
> Streamable HTTP：`url: http://127.0.0.1:8001/mcp` 加上
> `Authorization: Bearer ${env:API_TOKEN}`（可選 `type: "streamable-http"`），
> 並以 `./scripts/host-services.sh --driver=supervisord install mcp-http` 常駐
> （systemd／launchd 不支援）。stdio `command: ccas-mcp` 只在該 host 仍必須 spawn
> 子行程時使用。不要把真實 token 寫進 git 或對話；不要掛 deprecated HTTP+SSE
> （`/sse` + `/messages`）；不要把 bind 改成 `0.0.0.0` 或遠端 URL；不要新增寫入
> 工具。執行 `cd backend && uv sync`，確認無 Bearer 時 `GET /mcp` 為 HTTP 401，
> 然後依我指定的 MCP client 寫入其使用者設定。設定完成後列出實際修改的檔案、
> 連線方式（URL 或 stdio command）、六個 tools，以及測試結果；若缺少權限或
> client 名稱，停在可恢復的步驟並提出一個明確問題。

AI 執行時必須遵守：

- 先確認目標 client（Claude Desktop、Codex、Gemini CLI、Grok／Cursor 或其他）與
  設定檔位置，再寫入設定。能填 URL 的 host 優先 HTTP；stdio 是後援。
- 使用絕對 repository path；不要建立跨 repository symlink，也不要把 `.env`、token、
  credentials 或 MCP 設定中的秘密貼到對話或 commit。headers 只用
  `${env:API_TOKEN}` 插值。
- 設定前備份既有 client config；只新增 `mcpServers.ccas`，保留其他 server。
- HTTP 路徑：`install mcp-http`（或前景 `uv run ccas-mcp-http`）後做 401 smoke 與
  client 的 tool discovery。stdio 路徑：執行一次 `uv run ccas-mcp` 啟動檢查。
  失敗時保留錯誤輸出（遮罩秘密）並停止，不要反覆重試或刪除使用者設定。

若 AI 沒有本機寫檔或執行權限，請改用方式 A；AI 只能產生設定片段，不能代替使用者
在 GUI 中授權或輸入秘密。

## 專案內 GitNexus MCP

本 repository 的 [`.mcp.json`](../.mcp.json) 已提供 GitNexus server，供代理進行程式碼
探索與 impact analysis。它與 CCAS 業務 MCP 是兩個不同 server：

- `gitnexus`：程式碼知識圖譜，command 為 `npx -y gitnexus@1.6.3 mcp`。
- `ccas`：業務資料唯讀查詢。Grok／Cursor 家族用 loopback
  `http://127.0.0.1:8001/mcp`；stdio 後援為 `uv run ... ccas-mcp`。

不要以其中一個取代另一個。本機 loopback Streamable HTTP 已是支援的業務 MCP
通道；不要把任一個 server 改成**遠端**（非 loopback）HTTP endpoint。遠端連線必須
先有後續 ADR 的 Origin／token／scope 設計。

## 排錯

先區分 HTTP 與 stdio。Grok／Cursor 家族 host 應連 URL；升級後重裝 `mcp-http` 即載入
新碼，不必先殺 stdio PID。

| 可觀察結果 | 意義 |
|---|---|
| 無 Bearer 的 `/mcp` 回 HTTP 401 | smoke **PASS**（認證閘門活著） |
| 無 Bearer 卻 200／不是 401 | smoke **FAIL**；不要把 host 指過去 |
| 有效 Bearer 但 MCP session 404 | idle 逾時後 client 須重新 initialize，不是 query 失敗 |
| stdio `Not connected` 且 wire 無 JSON-RPC | host stale session；見下方 stdio 節 |

### 升級後改連 loopback HTTP

1. 若使用 host services：`./scripts/host-services.sh --driver=supervisord install mcp-http`
   （或 `install all`），再 `smoke mcp-http`（無 Bearer → 401）。
2. 將 host 設定改成 `url: http://127.0.0.1:8001/mcp` +
   `Authorization: Bearer ${env:API_TOKEN}`。
3. 依序等待 response：`tools/list` → `get_payment_due` → `pipeline_status`。
   `pipeline_status` 的 timestamp 須帶 UTC `Z`。
4. 可選：停掉舊的 stdio 子行程（見下一節）。HTTP 路徑不依賴那些 PID。

### 升級後 MCP 子行程殘留（stdio 後援）

stdio server 由 Agent host 建立子行程。`Restart`／`Add` 之後 host 可能仍顯示
connected，但實際連到升級前啟動的 `ccas-mcp` 或 logging wrapper。此時
`pipeline_status` 仍可能回舊的 `-32602 date-time`，即使 checkout 已是 v0.8.2+。

單靠 Restart **不能**保證載入新碼。每次 CCAS 升級後若仍用 stdio、或懷疑 session
殘留時：

1. 若本次有升 CCAS 且使用 host services，先重裝並 smoke，見
   [`non-docker-host-services.md`](non-docker-host-services.md)。
2. 確認殘留行程：

   ```bash
   pgrep -af 'ccas-mcp-logging-wrapper|ccas-mcp'
   ```

   清單裡的 `ccas-mcp-http` 是 supervisord 常駐 HTTP adapter，**不要**停它。

3. 只停 stdio／logging-wrapper（會中斷目前所有 `ccas-mcp` session）。
   `pkill -f ccas-mcp` 會連 `ccas-mcp-http` 一起殺掉，不要用那條：

   ```bash
   pkill -f 'ccas-mcp-logging-wrapper' || true
   pgrep -af 'ccas-mcp' | grep -v 'ccas-mcp-http'
   # 對上列剩餘的 stdio PID 再 kill
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

Grok／Cursor 家族請改連 loopback URL（見「首選」），不要再 spawn stdio。若必須留在
stdio：先做上一節的 PID 回收，再於 host 端移除或停止目前的 `ccas` MCP entry，重新
Add／Restart，執行 `tools/list` 後再逐次等待 response 呼叫 `get_payment_due`。

若新 session 的 server wire log 已收到 `tools/call` 且回傳 result，請將 host connector
的原始錯誤提交給該 host 的維護者；CCAS 端不需以 Redis、API 或 systemd 解法處理
這個 pre-roundtrip failure。

### `pipeline_status` 顯示 `-32602` 與 `date-time` validation

這表示 host 已收到 server response，但嚴格驗證 structured output 時拒絕沒有 timezone
offset 的 datetime。v0.8.2 會把 Agent datetime 統一輸出為 UTC `Z`，不需要資料庫
migration。若 checkout 已是 v0.8.2+ 仍出現此錯：HTTP 路徑重裝 `mcp-http`；stdio
路徑走「升級後 MCP 子行程殘留」，不要只 Restart。

### timeout smoke test 與實際 tool call

`timeout 3 uv run ccas-mcp` 只確認 stdio 長駐程序可以啟動，不會驗證 `tools/call`。
HTTP 路徑請用無 Bearer 的 `/mcp` → 401。若一次把多個 JSON-RPC request 寫入 stdio
stdin 後立即關閉 stdin，server 可能在 pending request 完成前收到 EOF，產生
`Connection closed`；完整驗證必須逐次寫入 request、等待 response，並保持 stdin
開啟直到最後一個 response 收到。

| 症狀 | 檢查 |
|---|---|
| `uv: command not found` | 安裝 uv，或改用已安裝的 Python/venv；不要直接使用系統 Python 猜測依賴。 |
| 找不到 `ccas-mcp`／`ccas-mcp-http` | 確認 command 的 `--directory` 指向 `ccas/backend`，並重新執行 `uv sync`。 |
| `mcp-http is only supported by supervisord` | 改 `--driver=supervisord`；不要用 systemd／launchd 跑 MCP HTTP。 |
| 無 Bearer 的 `/mcp` 不是 401 | HTTP adapter 未起來或聽錯 port；檢查 `MCP_HTTP_PORT` 與 supervisord log。 |
| client 顯示 JSON parse error（stdio） | 確認 stdout 沒有 shell banner、debug print 或 log。 |
| Restart 後仍跑舊碼或 `date-time` 錯 | HTTP：重裝 `mcp-http`。stdio：殺殘留 PID 再重接。 |
| tools 存在但查不到資料 | 啟動 CCAS backend、確認 data path 與登入狀態，再呼叫 `pipeline_status`。 |
| 需要寫入或同步 Notion | 目前契約不支援；遵守 ADR 的信任邊界，另行提出變更與授權設計。 |
| 需要遠端（非 loopback）MCP | 後續 ADR；不要把 `MCP_HTTP_HOST` 設成 `0.0.0.0`。 |
