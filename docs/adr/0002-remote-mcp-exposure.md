# ADR-0002: 遠端 MCP 暴露方式與授權模型

## Status

Proposed（草稿，待 Paul 拍板。本文件修訂 ADR-0001 第 6 點第 (3) 項；在被 Accept 前，
`docs/mcp-installation.md` 與程式碼仍以 loopback-only 為準，不得依本文件先行實作。）

## Context

ADR-0001 第 6 點把 MCP 連線分成三期：本機 stdio、本機 loopback Streamable HTTP、
遠端 Streamable HTTP。前兩期已落地（`ccas-mcp`、`ccas-mcp-http`），第三期被明確留給
「後續 ADR」。這份 ADR 就是那份後續 ADR。

現在需要決定第三期，是因為 MCP host 的使用情境已經不只在同一台機器上：Agent 可能跑在
手機端、雲端 host、或另一台桌機。目前的 `_require_loopback_host`（`backend/src/ccas/mcp/http.py`）
在行程啟動前就 fail-closed，任何非 loopback bind 都直接拒絕，所以「換台機器連」在今天
是完全不可能的。

這個決定具備 ADR 的典型特徵：

- **難以逆轉**：一旦有外部 Agent 依賴某個公開 endpoint 與授權模型，改變它會牽動不在
  本專案控制範圍內的 client。
- **有明確取捨**：直接 bind 對外最簡單，但把一台存有完整信用卡帳單資料的服務直接放上
  網路；tunnel 多一層依賴，但保留「行程只聽 loopback」這個硬性防線。
- **跨模組**：影響 transport security 設定、授權模型、部署腳本與所有未來的第三方整合。

技術上有一個容易被忽略、但會直接決定可行性的細節：目前 `TransportSecuritySettings`
的 `allowed_hosts` / `allowed_origins` 只列 `127.0.0.1` / `localhost` / `[::1]`
（DNS rebinding 防護）。任何 tunnel 都會帶著外部 `Host` header 進來，**現況會被這道
防護直接擋掉**。也就是說「只要架個 tunnel 就能用」是錯的，必須同時開放對外 hostname。

## 已查證的事實

以下四點在撰寫本 ADR 時實際驗證過，不是推論。它們直接決定可行性：

1. **DNS rebinding 防護今天就會擋掉 tunnel。**
   `mcp/server/transport_security.py` 的 `_validate_host()` 只接受 allowlist 的精確
   比對或 `base:*` 萬用埠比對。實測目前設定（`127.0.0.1:*` / `localhost:*` / `[::1]:*`）
   對 `Host: mcp.example.com` 與 `Host: mcp.example.com:443` 皆回 `False`。
   失敗碼：**Host 不合回 421**、**Origin 不合回 403**（後者符合 MCP 規格對 Origin 的要求）。

2. **`:*` 萬用字元不匹配沒有 port 的 Host。**
   實測：allowlist 只放 `mcp.example.com:*` 時，`Host: mcp.example.com:443` 通過，
   但 `Host: mcp.example.com` **不通過**。HTTPS 的 Host header 通常省略 443，所以
   只加 `:*` 條目會安靜地全部擋掉。必須同時加入 `mcp.example.com` 與 `mcp.example.com:*`。

3. **官方 Python SDK 沒有內建 JWT／JWKS／token introspection verifier。**
   `mcp/server/auth/provider.py` 只提供 `TokenVerifier` protocol 與委派給 in-process
   provider 的 `ProviderTokenVerifier`。任何「驗證外部 AS 簽發的 token」都得自己實作。

4. **Cloudflare Access Managed OAuth 簽發 opaque token，不是 JWT。**
   其 metadata endpoint 確實同時符合 RFC 8414 與 RFC 9728，但 access token 形如
   `oauth:CvNoo...`，無法由 client 或 origin 解碼；Cloudflare 在邊緣解析後改以
   `Cf-Access-Jwt-Assertion` header 把身分轉送到 origin。

## Decision

1. **遠端暴露一律走 tunnel，行程本身永遠只 bind loopback。**
   `_require_loopback_host` 不放寬。對外由 Cloudflare Tunnel／Tailscale 之類的通道
   連到 `127.0.0.1:<MCP_HTTP_PORT>`。理由：即使 tunnel 設定出錯或憑證外洩，作業系統
   層仍然沒有一個對外監聽的 socket；這是一道不依賴應用程式設定正確性的防線。
   **拒絕的替代方案**：放寬 bind 並由 nginx 反代。那會讓一個誤設的 `MCP_HTTP_HOST=0.0.0.0`
   直接等於公開暴露，把安全性押在單一環境變數上。

2. **新增 `MCP_PUBLIC_URL` 作為對外 canonical URI，並以它擴充 DNS rebinding 白名單。**
   未設定時行為與今日完全相同（純本機）。設定後，其 host 加入 `allowed_hosts`、
   `https://<host>` 加入 `allowed_origins`。URI 必須符合 RFC 8707 canonical form：
   有 scheme、無 fragment、不加尾斜線。

3. **授權由外部承擔，CCAS 不自建 authorization server。**
   **拒絕的替代方案**：以 SDK 的 `auth_server_provider` 在 CCAS 內建最小 AS。那會讓
   本專案承擔 token 簽發、輪替與撤銷的安全責任，與「CCAS 是一套可獨立部署的本機系統」
   的定位不符。

   具體要選哪一種外部授權，取決於下列三個**經查證**的選項。它們**不可互換**，成本
   與對 CCAS 程式碼的影響差距很大：

   | 選項 | MCP client 連到 | CCAS 需要驗證什麼 | 對現有程式碼的影響 |
   |---|---|---|---|
   | **A. Cloudflare MCP Server Portal**（建議） | portal URL | 不變：既有靜態 Bearer | **零**。`_ApiTokenVerifier` 原封不動 |
   | B. Cloudflare Access Managed OAuth | CCAS 的 public URL | `Cf-Access-Jwt-Assertion` header（非 Bearer） | 新增 JWT 驗證；Bearer 為 opaque token，無法自行解析 |
   | C. 標準 OIDC IdP（Auth0／Keycloak） | CCAS 的 public URL | Bearer JWT：簽章、`iss`、`aud`、`exp` | 新增 JWKS 驗證 + 明確宣告 `pyjwt[crypto]` |

   **選 A（Cloudflare MCP Server Portal）。** Portal 在 Cloudflare Access 後面集中多個
   MCP server，使用者在 portal 登入一次，portal 再以設定好的
   `Authorization: Bearer <token>` 轉送到 origin。也就是說**使用者身分驗證發生在
   portal，CCAS 這端維持今天的靜態 token 契約**——不需要寫 JWT 驗證、不需要新依賴、
   `_ApiTokenVerifier` 一行都不用改。Portal 明確支援 tunnel 後面的自架 remote HTTP
   MCP server，且只支援 remote HTTP（stdio 不行），正好對應 CCAS 已有的 Streamable
   HTTP adapter。

   代價要說清楚：選 A 之後，**安全邊界在 portal，不在 CCAS**。CCAS 的靜態 token 退化為
   portal 與 origin 之間的共享密鑰。這只有在決策 1（行程只 bind loopback、對外僅經
   tunnel）成立時才可接受——因為 origin 在網路上根本不可達，拿到該 token 的人也沒有
   路徑可以用。這兩個決策是綁在一起的，不能只採用其中一個。

   **選 B 的陷阱**：Cloudflare Access Managed OAuth 簽發的是 **opaque token**
   （形如 `oauth:CvNoo...`），不是 JWT，client 無法解碼，也沒有 JWKS 可驗。Cloudflare
   在邊緣把 token 解析成身分後，以 `Cf-Access-Jwt-Assertion` header 轉送到 origin，
   所以 CCAS 要驗的是**那個 header**，不是 Bearer。這與 MCP 規格「resource server 自己
   驗證 access token 的 audience」的字面要求有落差：實際上是邊緣代驗。同樣地，
   `validate_token_resource=True` 依賴 `AccessToken.resource`，opaque token 上沒有東西
   可填，所以 RFC 8707 的 audience 綁定在這條路上對不起來。

   **選 C 的前提**：RFC 8707 只把「audience-restrict 簽發的 token」列為 AS 的
   **SHOULD**，不是 MUST。因此 `validate_token_resource=True` 只有在**實測確認所選 AS
   真的會把 `resource` 綁進 token 的 `aud`** 之後才可開啟，否則會拒絕所有合法 token。
   另外官方 Python SDK **沒有**內建 JWT／JWKS／introspection verifier——只有
   `TokenVerifier` protocol 與委派給 in-process provider 的 `ProviderTokenVerifier`，
   驗證邏輯要自己寫。`pyjwt` 目前只是 `google-auth` 拉進來的傳遞依賴，採用選 C 必須
   比照 `cryptography>=42` 的前例在 `pyproject.toml` 明確宣告。

   無論選哪一條，`MCP_OAUTH_ISSUER_URL`（已存在，見 `openspec/specs/agent-mcp-interface/`）
   都是宣告 authorization server 的入口；選 A 不需要設定它。

4. **遠端仍然唯讀，secrets 邊界不放寬。**
   ADR-0001 第 3、5 點原封不動：沒有寫入工具，PDF 密碼／OAuth refresh token／
   session secret／完整卡號永不回傳。遠端不是放寬邊界的理由，反而是收緊的理由。

5. **不採用已 deprecated 的 HTTP+SSE transport（獨立 `/sse` + `/messages`）。**
   規格已將其列入移除登記。遠端仍只用 Streamable HTTP 單一 endpoint。

6. **tunnel 模式不經 nginx。**
   `docker/proxy/nginx.conf` 不新增 `/mcp` 路由。若日後改走 nginx，必須同時處理
   `proxy_buffering off` 與 `X-Accel-Buffering: no`，否則 Streamable HTTP 的 SSE
   回應會被緩衝而失去即時性。

## Consequences

**正面**

- 作業系統層沒有對外 socket，誤設環境變數不會等於公開暴露。
- CCAS 不需自建 AS，token 輪替與撤銷交給成熟的 IdP。
- 不需要為 MCP 另外處理 TLS 憑證：tunnel 端終結。

**需要承擔的代價**

- 多一個外部依賴（tunnel／portal 供應商）。該供應商中斷時遠端 MCP 不可用；本機 stdio
  與 loopback HTTP 不受影響，符合「關掉雲端仍要能用」的硬性前提。
- **選 A 的核心代價：安全邊界移到 portal。** CCAS 不再自行驗證使用者身分，只驗證一個
  共享 Bearer。這把「誰能存取帳單資料」的判斷完全交給 Cloudflare Access 政策設定正確。
  補償措施是決策 1：origin 在網路上不可達，所以該共享 token 外洩本身不構成可利用路徑。
- DNS rebinding 白名單被擴大，正確性從「只信 loopback」變成「信任 `MCP_PUBLIC_URL`
  的設定值」。設定錯誤的後果從「連不上」變成「多接受一個 Host／Origin」。
- 選 B／C 才會發生的代價：需要自行實作 token 驗證（SDK 沒有現成的），並且
  `validate_token_resource=True` 與真實 token 驗證必須同時上線。
  `test_audience_validation_tracks_the_token_verifier` 已把這兩件事綁在一起，
  漏做會在測試層失敗而非在線上沉默地接受錯誤 audience 的 token。
- 選 A 之下 MCP 規格「resource server 自行驗證 token audience」在字面上沒有被滿足
  （由 portal／邊緣代為完成）。這是刻意的取捨，必須在文件中寫明，不得宣稱 CCAS
  本身實作了 OAuth 2.1 resource server。

## Implementation Sketch（非決策內容，供 Accept 後參照）

- `backend/src/ccas/config.py`：`mcp_public_url: str = ""`
- `backend/src/ccas/mcp/http.py`：以 `mcp_public_url` 擴充 `TransportSecuritySettings`。
  **必須同時加入不帶 port 與帶 port 兩個條目**（見下方「已查證的事實」第 2 點）
- `deploy/host-services/supervisord/ccas-mcp-http.conf.in`：不變（仍 loopback）
- 新增 `docs/mcp-remote-access.md`：tunnel 設定、portal 設定、token 輪替與撤銷流程
- 測試：`mcp_public_url` 設定後白名單同時接受帶 port 與不帶 port 的 Host；
  未列入白名單的 Host 得 **421**；未列入白名單的 Origin 得 **403**；無 token 得 401
- 僅選 B／C 才需要：`_ApiTokenVerifier` 分裂為本機／遠端兩個實作，`_auth_settings()`
  在遠端模式改用 public URL 當 `resource_server_url`，並在實測 AS 確實綁 audience 後
  才開啟 `validate_token_resource`

## References

- `docs/adr/0001-agent-notion-trust-boundary.md` — 本 ADR 修訂其第 6 點第 (3) 項
- `openspec/specs/agent-mcp-interface/` 與 `.env.example` — `MCP_OAUTH_ISSUER_URL` 開關的規格與設定（由 `extend-agent-mcp-capability-surface` change 建立）
- `openspec/specs/agent-mcp-interface/` — MCP 介面 capability spec
- [MCP Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) — OAuth 2.1、RFC 9728 PRM、RFC 8707 resource、RFC 9207 iss
- [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) — Origin 驗證、localhost bind、`X-Accel-Buffering`、HTTP+SSE deprecation
- [Cloudflare MCP server portals](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) — 選項 A 的依據：tunnel 後自架 remote HTTP MCP server、portal 以 Bearer 轉送
- [Cloudflare Access Managed OAuth](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/) — 選項 B 的依據：opaque token 與 `Cf-Access-Jwt-Assertion`
- [Cloudflare: Secure MCP servers](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/secure-mcp-servers/) — customer-managed 與 SaaS-managed 兩種模式的差異
- [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html) — audience-restrict 對 AS 是 SHOULD 而非 MUST，決定選 C 的前提
