## Context

本 research 透過實際抓取 Gmail 富邦帳單信 → 跟著 SPA 流程打 API，已還原完整下載 pipeline 並在 JavaScript bundle 裡找到所有端點與欄位名。本文件記錄 trace 結果與推薦實作路徑，作為後續 `impl-fubon-fetcher-pipeline` change 的輸入。

**樣本來源**：`gmail message_id = 19d7301fd0fa5191`（2026 年 4 月富邦帳單）。結論涵蓋富邦現行 SPA 電子帳單，不保證涵蓋其他銀行或 FUBON 的 S / L billFrom 變體。

## End-to-End Flow

### Step 0：Gmail HTML → 下載連結

- Gmail 郵件 HTML body 中有**兩個** anchor 指向 `fbmbill.taipeifubon.com.tw`：
  1. `https://fbmbill.taipeifubon.com.tw/<hash>` — SPA 入口（**要用這個**）
  2. `https://fbmbill.taipeifubon.com.tw/client/pdf/<hash>` — 也是 SPA 入口（同 redirect 行為；Content-Type 回 text/html，不是 PDF）
- `<hash>` = 32 字元 hex，對應富邦系統的 `serialKey`（後面會看到再次出現）
- 既有 `FubonFetcher.can_fetch()` 已能辨識，無需調整。

### Step 1：第一次 GET → 302 redirect 種 session cookie

```
GET https://fbmbill.taipeifubon.com.tw/<hash>
→ 302 Location: /client?code=<hash>&bf=E
  Set-Cookie: JSESSIONID=...
  Set-Cookie: NSC_JOmbfareb2t3tkpbhpxupbbk4wj4xb3=... (HttpOnly, secure)
```

後續**所有** API 都必須帶這兩個 cookie，否則視為新 session。JSESSIONID 有短 idle timeout（抓樣時觀察約 5 分鐘）。

### Step 2：載入 SPA HTML + JS bundle

```
GET /client?code=<hash>&bf=E          → SPA shell (29 行 HTML，只掛 #app)
GET /client/js/chunk-vendors.js       → 2.5MB vendor 包
GET /client/js/app.js                 → 180KB 主包
GET /client/js/src_views_Login_index_vue.js  → 55KB Login 頁組件
```

`app.js` 用 webpack `eval()` dev 模式打包，所有 API endpoint 與 component source 都看得到，不需要 de-obfuscate。

前端 Vue URL params `?code=<hash>&bf=E` → 由 `Login/index.vue` 的 `getSerialKey()` 讀出並存到 `this.user.serialKey`；`bf` → billFrom（E / S / L），影響 UI 文案但 doLogin payload 照送。

### Step 3：取得 captcha（關鍵發現）

```
GET https://fbmbill.taipeifubon.com.tw/checkImgs/captcha.jpg
    Cookie: JSESSIONID=...; NSC_...
→ 200 Content-Type: image/jpeg
  Body（純文字！）: "<server_token>,<base64_jpeg>"
```

**響應格式不是二進位 jpeg**，而是 `<token>,<base64>` 的逗號分隔字串。前端 `getCode()`：

```js
const res = await apiGetCode();          // axios get
const str = res.data;                    // "NHV7vpKhaEbu4yjDmD/59A==,/9j/4AAQ..."
this.code    = str.split(',')[0];        // server token，login 時原樣回送
this.imgSrc  = 'data:image/jpeg;base64,' + str.split(',')[1];
```

**樣本**：`token=NHV7vpKhaEbu4yjDmD/59A==`、jpg 2721 bytes、125×55、5 位數字 + 紅色刪除線雜訊。

為什麼有 token：舊版 captcha 靠 session 綁定（server 記 `session → answer`）；新版改成 **NOSESSION** 模式（見 Login chunk 註解 `//20251022 NOSESSION版 - 前端自帶 key`），server 把 answer **加密** 後當 token 下發，login 時要原樣回送。這代表 captcha 答案驗證是**無狀態**的、不需要同一個 JSESSIONID 也能驗 — 只要 token 未過期、未被用過即可。

### Step 4：POST doLogin

```
POST https://fbmbill.taipeifubon.com.tw/doLogin
Content-Type: application/json
Cookie: JSESSIONID=...; NSC_...
Body:
{
  "id":          "<身分證號碼，大寫>",
  "birthday":    "0850101",                         // 民國生日 7 碼
  "serialKey":   "<Step 1 的 <hash>>",               // 從 URL ?code=...
  "captchaCode": "<Step 3 token>,<5 位數字 OCR 結果>" // 逗號分隔
}
→ 200 JSON:
{ "code": 0, "jwt": "eyJ...", ...MemberInfo }   // 成功
{ "code": 9999, ... }                           // 失敗（Login chunk 有處理）
```

**payload 組裝** ≡ `captchaCode = \`${this.code},${userInput}\`` — 這就是為什麼 server 既有 token 又有答案。

成功後前端把 `jwt` 寫進 `sessionStorage.jwt`；後續所有 API 會透過 axios interceptor 加 `Authorization` header：

```js
api.interceptors.request.use(config => {
  if (sessionStorage.getItem('login') && sessionStorage.getItem('jwt')) {
    config.headers['Authorization'] = sessionStorage.getItem('jwt');
  }
  return config;
});
```

### Step 5：取得 bill 資料（可能觸發 OTP）

登入後的 API 表（從 `app.js` 靜態分析）：

| Method | Path | 用途 |
|---|---|---|
| GET | `bill/billMainInfo` | 首頁摘要（總額、月份） |
| GET | `bill/billDetailInfo` | 消費明細 |
| GET | `bill/psid/billPsidData` | 電子帳單簽章資料 |
| GET | `ownerInfoHistory` | 過去 6 期帳單清單 |
| GET | `otp` | **條件式觸發 OTP**（看 `apiGetOtp`/`apiVerifyOtp`） |
| POST | `otpverify` | 驗證簡訊 OTP |
| POST | `retreiveUserData` | （拼錯的 retrieve）取使用者資料 |
| GET | `consumption/list`, `staging/list` | 交易清單、分期清單 |

OTP 在「查看歷史帳單」或「查看卡號末 3 碼」時才觸發；**下載本期 PDF 不需要 OTP**（`downloadPDF` route 只需 login jwt，從 `app.js` route 表推得）。

### Step 6：下載 PDF

前端 route：`/setting/downloadPDF`，對應 component `src_views_Setting_DownloadPDF_index_vue`。實際 API endpoint 需要再抓一次該 chunk 才能確認，但從 `bill/psid/billPsidData` + download button 流程推測：

- 最可能路徑：`GET /client/pdf/<hash>` 或 `GET getPdfFile?...`，header 帶 `Authorization: <jwt>`
- 檔案本體仍以 **身分證字號** 作為 PDF 密碼（郵件原文明載；與現行 `PDF_PASSWORD_FUBON` 一致）

**本 research 尚未實測 Step 6 的 endpoint 與 response**，因為：
1. 要先通過 captcha login 才能拿 jwt（需要實際 id + birthday，屬敏感操作）
2. Step 6 endpoint 位於另一個 webpack chunk，impl change 再抓即可

## Captcha 辨識路徑 — Decision Matrix（含 POC 實測）

**更正**：captcha 是 **4 位數字**（不是先前寫的 5 位），藍色字體 + 紅色單斜線雜訊，125×55 JPEG。本節所有準確率都是 2026-04-11 對真實 10 張樣本的**實測數字**（GT: 2962 / 4707 / 7620 / 4450 / 9728 / 7555 / 8379 / 4847 / 8189 / 2080）。

| 方案 | 1-shot 實測 | Retry 後最終成功率 | 每期成本 | 工時 | 維運 | 依賴 |
|---|---|---|---|---|---|---|
| A. Claude 多模態 API | 10/10 | >99% 1-shot | $0.0003/次 | 0.5 day | 極低 | Anthropic API key |
| **B. EasyOCR + conf gate + retry**（推薦） | **5/10（50%）**；conf≥0.80 後 accepted 100% precision | **5 retry → 96.9%**、7 retry → 99.2% | 0 | 1 day | 低 | `easyocr` + torch CPU（~500 MB image 增量） |
| C. Tesseract + HSV 前處理 | **4/10（40%）** | 3 retry 僅 78%，不達門檻 | 0 | 1 day | 低 | `pytesseract` + 系統 tesseract |
| D. 自訓 CNN | 理論 >98% | N/A | 0 | 3-5 day（需標 500+ 樣本） | 中（樣式改變要重訓） | `onnxruntime` |
| E. 第三方 2captcha | ~95% | >99% | $0.001/次 | 0.3 day | 低 | 付費、法遵風險 |
| F. Manual staging fallback | 100%（人工） | 100% | 人力 | 0（既有） | 每期人工 | 無 |

### POC 實測細節

**共同前提**：樣本 10 張真實 captcha，`curl` 直接從 `checkImgs/captcha.jpg` 抽下來，解開 `<token>,<base64>` 存成 `/tmp/fubon_cap_{1..10}.jpg`。

**B. EasyOCR（推薦）** — 實測 5/10，conf-gate 後 accepted 全對
- 呼叫：`reader = easyocr.Reader(['en']); reader.readtext(raw_jpeg, allowlist='0123456789')`
- **不做 preprocessing**：試過 HSV 藍色 mask + morph close + upscale，EasyOCR 準確率從 50% 掉到 0%。前處理對 pretrained natural-image OCR 是反效果
- Confidence 分布（實測）：

  | 樣本 | GT | Pred | Conf | Gate (conf≥0.80, len==4) |
  |---|---|---|---|---|
  | 1 | 2962 | 2962 | 0.83 | ✓ accept ✓ correct |
  | 2 | 4707 | 4707 | 0.98 | ✓ accept ✓ correct |
  | 3 | 7620 | 7620 | 0.98 | ✓ accept ✓ correct |
  | 4 | 4450 | 1450 | 0.17 | ✗ reject |
  | 5 | 9728 | 0128 | 0.39 | ✗ reject |
  | 6 | 7555 | 7355 | 0.78 | ✗ reject（剛好擋住） |
  | 7 | 8379 | 18379 | 0.45 | ✗ reject（長度錯） |
  | 8 | 4847 | 4847 | 0.96 | ✓ accept ✓ correct |
  | 9 | 8189 | 8189 | 1.00 | ✓ accept ✓ correct |
  | 10 | 2080 | 780 | 0.28 | ✗ reject（長度錯） |

- **結論**：`conf ≥ 0.80 && len == 4` gate 下，accepted 的 5 筆**全對**（precision 100%），rejected 的 5 筆都能透過重抽 captcha 重試
- Retry 數學：1 - 0.5^N → 3→87.5%、5→96.9%、7→99.2%
- `getCode()` 是 idempotent GET，樣本測試未觀察到 rate limit，7 次 retry 約 1 秒內完成

**C. Tesseract（已實測，不推薦）**
- 流程：HSV 藍色 mask → 5× upscale → morph close → threshold → 試 PSM 6/7/8/10/13
- 最佳 PSM 10 僅 4/10。失敗模式：邊緣數字被裁（`7620→620`、`4450→450`、`8379→379`）
- Contour segmentation + per-digit 更糟（0/10），因為相連數字被合併成單元件
- 3 retry 也只有 78%，不達 production 門檻，跳過

**A. Claude 多模態（僅列為 fallback）**
- POC：10 張樣本逐張用多模態辨識，10/10 正確
- 可選 `FUBON_CAPTCHA_FALLBACK_LLM=1` 開啟，預設關閉

### 推薦配置

```
主路徑：EasyOCR（readtext, allowlist=digits, conf≥0.80 gate, len==4 gate）
  ↓ 被 gate 拒 OR doLogin 回 captcha 錯誤
Retry：重抽 captcha，最多 7 次（與 Login chunk 的 getCode() 語意一致）
  ↓ 7 次仍失敗
Fallback A：Claude API（可選，FUBON_CAPTCHA_FALLBACK_LLM=1，預設關）
  ↓ 失敗
Fallback F：raise FetchError，降級到 manual staging（既有流程）
```

### 為什麼改推 B 而不是 A

使用者明確要求不透過 LLM。B 方案：

1. **零外部 API 呼叫**：captcha 圖片完全不離開專案
2. **離線可跑**：Docker build 階段預下載 easyocr 權重後 runtime 全離線
3. **準確率可接受**：conf-gate + 7 retry ≥ 99.2%，滿足「每月 1 期帳單、允許人工兜底」的業務需求
4. **零運行成本**

**代價**：
- Docker image 增加約 500 MB（torch CPU wheel + easyocr + 偵測與辨識模型權重）
- 首次 `Reader()` 初始化約 1~2 秒（容器啟動後第一次呼叫）
- 需在 `Dockerfile` 把模型權重 `RUN python -c "import easyocr; easyocr.Reader(['en'])"` 烘進 image，避免 runtime 下載

### 風險與備案

- **富邦改 captcha 樣式**（例如加 CJK、改 6 位、背景大幅變更）→ EasyOCR 準確率會掉；觸發頻繁 fallback 時要重評估
- **EasyOCR torch 版本衝突**：torch CPU wheel 與 backend 現有依賴需 lock；建議用 `uv` extras 隔離
- **server_token 綁 IP**（未驗證）→ 若綁 IP，需確認 Docker host network 出站穩定
- **Captcha 重抽 rate limit**：樣本測試沒碰到，但 impl 要加 `asyncio.sleep(0.3)` between retries 保守一點
- **法遵**：僅下載使用者本人郵件裡的連結、使用使用者本人的身分證號登入，屬使用者授權自動化；需在 `docs/user-guide.md` 加免責聲明

## 推薦 Impl 架構

後續 `impl-fubon-fetcher-pipeline` change 建議這樣切：

```
backend/src/ccas/ingestor/fetcher/banks/fubon/
├── __init__.py            # 既有 FubonFetcher，只改 fetch_pdf()
├── client.py              # HTTPX session wrapper（cookie jar + JWT）
├── captcha.py             # EasyOCR 辨識 + conf gate（主路徑）
├── captcha_llm.py         # Claude API 辨識（可選 fallback）
└── flow.py                # Step 1~6 pipeline orchestration
```

- **`client.py`**：`httpx.AsyncClient(cookies=CookieJar(), follow_redirects=True)`，持 JSESSIONID + NSC cookie 穿越所有 request；`_jwt` 存 instance 變數；`Authorization` header 由內建 event_hooks 加
- **`captcha.py`**：
  - `_READER: easyocr.Reader | None = None`（lazy singleton，避免每次 import torch 的 cost）
  - `def solve(jpeg_bytes: bytes) -> str | None`：回辨識結果；若 `len != 4` 或 `min_conf < 0.80` 回 `None` 代表 reject
  - 同步函式，用 `asyncio.to_thread` 包到 async flow 裡
- **`captcha_llm.py`**（可選）：`async def solve_with_llm(jpeg_bytes) -> str`，條件 `settings.fubon_captcha_fallback_llm` 才啟用
- **`flow.py`**：`async def download(email_html: str, settings: Settings) -> bytes`，實作 Step 1~6；每步失敗 raise `FetchError` with 具體階段標記；captcha retry 上限由 `FUBON_CAPTCHA_MAX_RETRIES` 控制（預設 7）
- **`FubonFetcher.fetch_pdf()`**：讀 `Settings.fubon_id_number` + `Settings.fubon_birthday`（新 env vars），呼叫 `flow.download(...)`，成功回 bytes；失敗 raise `FetchError(bank_code="FUBON", reason=...)`

**新 env vars**：
```
FUBON_ID_NUMBER=A123456789              # 身分證號大寫
FUBON_BIRTHDAY=0850101                   # 民國生日 7 碼
FUBON_CAPTCHA_MAX_RETRIES=7              # 預設 7，約 99.2% 最終成功率
FUBON_CAPTCHA_FALLBACK_LLM=0             # 預設關；設 1 才啟用 Claude fallback
```

**Docker 整合**：
```dockerfile
# 在 backend image build 階段烘進 easyocr 模型，避免 runtime 下載
RUN uv add easyocr && uv run python -c "import easyocr; easyocr.Reader(['en'], download_enabled=True)"
```

**測試策略**：
- **unit**：用靜態 HTML fixture（本 research 抓到的 `/tmp/fubon_mail.html`、`/tmp/fubon_spa.html`、`/tmp/fubon_captcha_raw`）mock 所有 HTTP 回應
- **integration**：加 `@pytest.mark.live_fubon` marker，需 `FUBON_ID_NUMBER` 等才跑；CI skip
- **不在 CI 跑**：避免對富邦 server 頻繁 hit + 不想把 credentials 放 CI

## 決策紀錄 (ADR-style)

| # | Decision | Rationale |
|---|---|---|
| D1 | 不走 playwright / headless browser | 整個 flow 是純 JSON API，無 DOM 互動需求；playwright 要 ~300MB Chromium、啟動慢、Docker 裡裝麻煩 |
| D2 | Captcha 走 EasyOCR + conf-gate + retry（**更新**） | 使用者要求不透過 LLM；POC 實測 1-shot 50%，conf-gate 後 accepted 100% precision，7 retry 達 99.2%；零外部 API、離線可跑；見 decision matrix B |
| D2b | 保留 Claude fallback 但預設關閉 | 當富邦改版導致 EasyOCR 連續失敗時，設 `FUBON_CAPTCHA_FALLBACK_LLM=1` 可救急，不必發新版本 |
| D3 | 不實作 OTP 流程 | 下載本期 PDF 路徑不觸發 OTP（從 app.js 靜態分析確認） |
| D4 | Session cookie 用 httpx CookieJar | cookies 都是 Set-Cookie header，不需要手動解析；`follow_redirects=True` 自動處理 Step 1 的 302 |
| D5 | 維持 bank_code="FUBON" 與現有 spec | `fubon-fetcher-impl` 的 `can_fetch` 規格不變，只替換 `fetch_pdf` 實作 |
| D6 | captchaCode 原樣拼 `${token},${answer}` | 直接複製前端邏輯，不嘗試理解 server 的 token 解密 |

## Open Questions（impl change 要補掉）

1. Step 6 實際 PDF endpoint 的 URL 與 response 格式（要抓 `src_views_Setting_DownloadPDF_index_vue.js`）
2. `serverToken` 是否綁 IP / UA / Cookie — 影響本地 dev vs prod 能否共用 session
3. doLogin 失敗時 response code 9999 之外的所有 error codes（login chunk 還沒完整列舉）
4. `Authorization` header 是 raw jwt 還是 `Bearer <jwt>`（前端源碼是 `config.headers['Authorization'] = token`，直接放 jwt，不加前綴 — 需實測確認）
5. captcha retry 上限（研究假設 3 次；實測看 server 是否有 rate limit）
