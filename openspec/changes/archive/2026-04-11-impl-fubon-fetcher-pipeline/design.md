## Context

實作 FUBON 自動下載 pipeline。所有研究結論（HTTP flow、payload schema、captcha OCR POC、架構建議）見 `openspec/changes/research-fubon-web-fetch-pipeline/design.md`。本文件只記錄**落地決策**：模組切分、錯誤型別、測試策略、相容性、踩雷紀錄。

## Module Layout

```
backend/src/ccas/ingestor/fetcher/banks/fubon/
├── __init__.py            # FubonFetcher class (既有)，只改 fetch_pdf()
├── client.py              # HTTPX session wrapper
├── captcha.py             # EasyOCR 辨識 + conf gate（主路徑）
├── captcha_llm.py         # Claude API 辨識（可選 fallback，lazy import）
├── flow.py                # Step 1~6 pipeline orchestration
└── errors.py              # FubonFlowError 子類（映射到通用 FetchError）
```

**為什麼拆這麼細**：每個檔案職責單一，unit test 只需 mock 單一邊界；HTTP client 與 captcha OCR 可各自演進而不互相影響；Claude fallback 放獨立檔案確保主路徑完全不 import `anthropic` SDK。

## Interfaces

### `FubonClient`（`client.py`）

```python
class FubonClient:
    """httpx.AsyncClient 的 thin wrapper，管理 cookie jar + JWT。"""

    def __init__(self, *, timeout: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            cookies=httpx.Cookies(),
            headers={"User-Agent": _UA_SAFARI},
        )
        self._jwt: str | None = None

    async def __aenter__(self) -> "FubonClient": ...
    async def __aexit__(self, *exc: object) -> None: ...

    async def open_spa(self, serial_key: str) -> None:
        """Step 1: GET /<hash>，自動 follow 302，種 JSESSIONID + NSC cookie。"""

    async def get_captcha(self) -> tuple[str, bytes]:
        """Step 3: GET checkImgs/captcha.jpg → (server_token, jpeg_bytes)。"""

    async def do_login(
        self,
        *,
        id_number: str,
        birthday: str,
        serial_key: str,
        captcha_token: str,
        captcha_answer: str,
    ) -> None:
        """Step 4: POST doLogin；成功後設 self._jwt。"""

    async def get_bill_pdf(self, serial_key: str) -> bytes:
        """Step 6: 走登入後的 PDF download endpoint，回 PDF bytes。"""

    async def _post(self, path: str, json: dict) -> httpx.Response:
        """內部 wrapper — 自動加 Authorization header（若 self._jwt 存在）。"""
```

**踩雷 / 注意**：
- `follow_redirects=True` 必開，因為 Step 1 的 302 要自動跟（否則 cookie 不會種）
- `httpx.Cookies()` 要明確 pass，否則 default cookie jar 不會跨 request 持有
- JWT 不加 `Bearer ` 前綴（前端原始碼直接 `config.headers['Authorization'] = token`）
- User-Agent 用 Safari 避免被 WAF 擋（研究階段 curl 用 macOS Safari UA 沒問題）

### `captcha.solve`（`captcha.py`）

```python
from dataclasses import dataclass
import easyocr  # module-level import OK，torch 在 backend dep 裡

_READER: easyocr.Reader | None = None
_MIN_CONF = 0.80
_EXPECTED_LEN = 4

@dataclass(frozen=True)
class CaptchaResult:
    text: str          # 4 位數字
    confidence: float  # 最低 conf

def _get_reader() -> easyocr.Reader:
    global _READER
    if _READER is None:
        _READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _READER

def solve(jpeg_bytes: bytes) -> CaptchaResult | None:
    """EasyOCR 辨識 + conf gate。返回 None 代表被 gate 拒絕（呼叫端應 retry）。"""
    import numpy as np
    import cv2

    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    reader = _get_reader()
    results = reader.readtext(img, allowlist="0123456789", detail=1)
    text = "".join(r[1] for r in results).replace(" ", "")
    min_conf = min((r[2] for r in results), default=0.0)

    if len(text) != _EXPECTED_LEN or not text.isdigit():
        return None
    if min_conf < _MIN_CONF:
        return None
    return CaptchaResult(text=text, confidence=min_conf)
```

**決策**：
- Module-level `_READER` singleton — 避免每次重建 torch 模型（~1 秒）
- **不做前處理**：POC 確認前處理讓準確率從 50% 降到 0%
- `solve()` 是**同步函式**，flow 側用 `asyncio.to_thread(solve, jpeg)` 包進 async context
- `import cv2 / numpy` 留在函式內 lazy — 避免 `captcha.py` 被 import 就拖 torch 啟動時間
- 不 expose `_MIN_CONF` / `_EXPECTED_LEN` 為環境變數 — 避免使用者誤調降低 gate 破壞正確率；要調就改 code

### `captcha_llm.solve_with_llm`（`captcha_llm.py`）

```python
async def solve_with_llm(jpeg_bytes: bytes) -> str:
    """僅在 FUBON_CAPTCHA_FALLBACK_LLM=1 時被 flow 呼叫。

    Raises CaptchaLlmError on any failure (network, parse, API key missing).
    """
    try:
        import anthropic  # lazy，主路徑不引入
    except ImportError as e:
        raise CaptchaLlmError("anthropic SDK not installed") from e
    ...
```

**決策**：
- `anthropic` **不**加到 `pyproject.toml` 主依賴，改用 `[project.optional-dependencies]` 的 `fubon-llm` extra，避免沒開 fallback 的使用者被迫安裝
- 若 `settings.fubon_captcha_fallback_llm=1` 但沒裝 extra → flow 在啟動時就 raise，不等到 runtime

### `flow.download`（`flow.py`）

```python
async def download(
    *,
    email_html: str,
    settings: Settings,
) -> bytes:
    """Step 1~6 pipeline。"""
    serial_key = _extract_serial_key(email_html)  # regex 抓 /<32hex>

    async with FubonClient() as client:
        await client.open_spa(serial_key)
        jwt_acquired = await _login_with_captcha_retry(
            client=client,
            id_number=settings.fubon_id_number,
            birthday=settings.fubon_birthday,
            serial_key=serial_key,
            max_retries=settings.fubon_captcha_max_retries,
            llm_fallback=settings.fubon_captcha_fallback_llm,
        )
        if not jwt_acquired:
            raise FetchError(
                "FUBON captcha 重試全部失敗",
                bank_code="FUBON",
                reason="captcha_retry_exhausted",
            )
        return await client.get_bill_pdf(serial_key)
```

**關鍵私有函式**：

```python
async def _login_with_captcha_retry(
    *,
    client: FubonClient,
    id_number: str,
    birthday: str,
    serial_key: str,
    max_retries: int,
    llm_fallback: bool,
) -> bool:
    for attempt in range(max_retries):
        token, jpeg = await client.get_captcha()

        # 主路徑：EasyOCR
        result = await asyncio.to_thread(captcha.solve, jpeg)

        # Fallback：LLM（僅 llm_fallback=True 且 OCR 失敗後）
        if result is None and llm_fallback:
            from ccas.ingestor.fetcher.banks.fubon import captcha_llm
            try:
                llm_text = await captcha_llm.solve_with_llm(jpeg)
                result = captcha.CaptchaResult(text=llm_text, confidence=1.0)
            except captcha_llm.CaptchaLlmError:
                result = None

        if result is None:
            await asyncio.sleep(0.3)  # 保守 rate limit
            continue

        try:
            await client.do_login(
                id_number=id_number,
                birthday=birthday,
                serial_key=serial_key,
                captcha_token=token,
                captcha_answer=result.text,
            )
            return True
        except FubonLoginError as e:
            if e.code == "captcha_wrong":
                await asyncio.sleep(0.3)
                continue
            raise  # id / birthday 錯誤直接 raise，不 retry

    return False
```

## Settings 擴充

```python
# backend/src/ccas/config.py 加入：

class Settings(BaseSettings):
    ...
    fubon_id_number: str | None = None
    fubon_birthday: str | None = None
    fubon_captcha_max_retries: int = 7
    fubon_captcha_fallback_llm: bool = False

    @field_validator("fubon_id_number")
    @classmethod
    def _validate_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.fullmatch(r"[A-Z][12]\d{8}", v):
            raise ValueError("FUBON_ID_NUMBER must be 10 chars: [A-Z][12]\\d{8}")
        return v

    @field_validator("fubon_birthday")
    @classmethod
    def _validate_birthday(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.fullmatch(r"0\d{6}", v):
            raise ValueError("FUBON_BIRTHDAY must be ROC 7 digits (e.g. 0850101)")
        return v
```

**決策**：env vars 預設 `None` 而非必填 — 讓沒 FUBON 的使用者也能跑 backend；fetcher 自己在 `fetch_pdf()` 入口檢查並 raise `FetchError("FUBON credentials not set")`。

## Error Hierarchy

```
FetchError (既有，ccas.errors)
  └─ raised by FubonFetcher.fetch_pdf() 向外層 pipeline 暴露

FubonFlowError (新，fubon/errors.py) — 內部用，不外洩
  ├─ FubonRedirectError   # Step 1 302 異常
  ├─ FubonSessionError    # cookie 沒種成功
  ├─ FubonLoginError      # doLogin 回 code != 0；.code 欄位分類（captcha_wrong / id_wrong / ...）
  └─ FubonPdfError        # Step 6 下載失敗
```

Flow 層捕捉 `FubonFlowError` 子類並轉成 `FetchError(bank_code="FUBON", reason=<子類名>)`。

## Test Strategy

### Unit tests（mock HTTP）

Fixture 資料來自 research change 抓下的真實檔案：

```
backend/tests/fixtures/fubon/
├── mail_with_link.html        # research /tmp/fubon_mail.html 的子集
├── spa_shell.html             # /tmp/fubon_spa.html
├── captcha_samples/           # 10 張 /tmp/fubon_cap_*.jpg
│   ├── 2962.jpg
│   ├── 4707.jpg
│   └── ...
└── captcha_response.txt       # <token>,<base64> 格式樣本
```

**檔案與最低測試數**：

| 測試檔 | 必須 cover 的 scenario |
|---|---|
| `test_client_open_spa.py` | 302 redirect 跟隨、cookie jar 持有、非 FUBON URL 拒絕 |
| `test_client_get_captcha.py` | response 切分 `<token>,<base64>`、b64 decode 正確 |
| `test_client_do_login.py` | payload JSON schema、JWT 存到 client、失敗 code 對映 |
| `test_captcha_gate.py` | 10 張樣本全跑一次、確認 accepted 5 張全對、rejected 5 張都回 None |
| `test_flow_retry.py` | mock OCR 前 N 次回 None，第 N+1 次成功，doLogin 被呼叫 |
| `test_flow_retry.py` | mock OCR 全失敗達 `max_retries`，raise `FetchError(reason=captcha_retry_exhausted)` |
| `test_flow_id_error.py` | OCR 成功但 doLogin 回 id_wrong，不 retry，立刻 raise |
| `test_captcha_llm_lazy.py` | `llm_fallback=False` 時 `anthropic` 不被 import（用 `sys.modules` 檢查） |

### Integration test（手動觸發）

```python
@pytest.mark.live_fubon
async def test_live_download(tmp_path, settings_with_fubon_creds):
    """需 env 有 FUBON_ID_NUMBER/FUBON_BIRTHDAY；CI 不跑。"""
    from ccas.ingestor.fetcher.banks.fubon import FubonFetcher
    fetcher = FubonFetcher()
    email_html = (FIXTURE / "mail_with_link.html").read_text()
    pdf_bytes = await fetcher.fetch_pdf(email_html=email_html, settings=settings)
    assert pdf_bytes.startswith(b"%PDF")
```

**CI 設定**：`pytest -m "not live_fubon"` 為預設；`conftest.py` 註冊 marker；跑 live 測試要 `pytest -m live_fubon` 並有 credentials 才跑。

## Dependency Strategy

### `pyproject.toml`

```toml
[project]
dependencies = [
    ...,
    "easyocr>=1.7.2",     # 含 torch, torchvision, opencv-python-headless
]

[project.optional-dependencies]
fubon-llm = ["anthropic>=0.40.0"]
```

**決策**：
- `easyocr` 放主依賴 — 因為所有 FUBON 使用者都會用到
- `anthropic` 放 optional — 只有開 fallback 的使用者才裝
- 不加 `opencv-python`（easyocr 依賴的是 `headless` 版本，不要衝突）

### `Dockerfile`

在 backend image build 最後加：

```dockerfile
# Pre-warm EasyOCR 模型權重，避免 runtime 下載
RUN uv run python -c "import easyocr; easyocr.Reader(['en'], gpu=False, download_enabled=True)"
```

**結果**：image 增 ~500 MB（torch CPU wheel + easyocr craft_mlt_25k.pth + english_g2.pth）。accepted，FUBON 是必要功能。

## User Guide 更新

`docs/user-guide.md` FUBON 章節加：

```markdown
### FUBON 富邦銀行設定

富邦帳單系統為 SPA + 圖形驗證碼流程。自動下載需要以下設定：

```env
FUBON_ID_NUMBER=A123456789      # 你的身分證號（英文字母大寫）
FUBON_BIRTHDAY=0850101           # 民國生日 7 碼（例：民國 85 年 1 月 1 日）
FUBON_CAPTCHA_MAX_RETRIES=7      # 選填，預設 7
FUBON_CAPTCHA_FALLBACK_LLM=0     # 選填，預設關閉
```

**免責聲明**：本自動化流程僅下載使用者本人 Gmail 中的帳單連結、使用
使用者本人的身分證號與生日進行登入，屬使用者授權的自動化代理。若你
不希望啟用，留白即可；未設定 credentials 時 fetcher 會明確 raise
`FetchError("FUBON credentials not set")`，不影響其他銀行。
```

## ADR (新決策，research design ADR 之外的)

| # | Decision | Rationale |
|---|---|---|
| I1 | `easyocr` 放主依賴 | 90% FUBON 使用者會用；放 optional 讓 docker build 變成兩階段太複雜 |
| I2 | `anthropic` 放 optional extra | 只有 <10% 會開 LLM fallback；避免無辜增加 image size |
| I3 | Settings env vars 預設 `None` | 允許沒 FUBON 的使用者跑 backend，fetcher 自己檢查 |
| I4 | `_MIN_CONF=0.80` / `_EXPECTED_LEN=4` hardcoded | 避免使用者誤調降低 gate；要改就 PR |
| I5 | Rate limit `sleep(0.3)` 保守值 | 樣本測試沒觀察到 rate limit，但為富邦 server 友善 |
| I6 | Fixture 走 `/tmp` → `backend/tests/fixtures/` | Research 用的暫存檔是 `/tmp`；impl 階段搬進 repo，commit 時遮蔽個人資料（email HTML 要遮敏感 headers） |
| I7 | 不 mock `easyocr.Reader`，直接跑真模型 | Unit test 載入 reader 約 1 秒；`pytest --lf` 通常只跑變動的，可接受；好處是不會因為 mock 漂移錯過真正的 bug |

## Open Questions

### Resolved

1. **Step 6 PDF endpoint** ✅ — 2026-04-11 透過下載 `src_views_PDF_index_vue.js` + `src_views_Setting_DownloadPDF_index_vue.js` 兩個 webpack chunk 確認：
   - **Method**: `GET`（`apiGetBlob` → `api.get` with `responseType: 'blob'`）
   - **URL**: `/PDFReportProc`（axios `baseURL: "/"`，相對 host root）
   - **Query params**: `billPeriod`、`batchPeriod`、`id`（= `uniqueIdentifier`）、`twYearMonth`
   - **Headers**: `Authorization: <jwt>`（**raw token，非 `Bearer <jwt>`**，由 app.js 的 request interceptor 注入）
   - **Prerequisite**: `billPeriod` / `batchPeriod` / `id` / `twYearMonth` 要先 call `GET /bill/billMainInfo` 取得；`mainInfo.uniqueIdentifier` 對應到 `id` param
   - **踩雷**: app.js 的 `req()` helper 對 `'get'` 方法**實際發 POST**（`case 'get': return api.post(url, data, config)`），但 `apiGetBlob` 繞過 `req()` 直接用 `api.get`，故 PDFReportProc 確實是 GET。Client 實作時要區分：凡是走 `req('get', ...)` 的 endpoint（包括 `bill/billMainInfo`）都是 POST + JSON body，不是 GET + query string。

### Pending（需 live login，留待 tasks.md 0.2/0.3/0.4 解）

2. **`FubonLoginError.code` 對映表** — `code: 0` 成功、`9999` 是 captcha_wrong（Login chunk 已確認 `1001` 家族為 id/birthday 相關），但實際 mapping 要用真 credentials 故意輸入錯誤抓 response。
3. **Captcha rate limit** — 研究時 10 次無阻擋；impl 前要連續測 30 次觀察 429/403。
4. **JWT TTL** — 實測 `doLogin` → `bill/billMainInfo` 間隔 5/15/30/60 秒各一次，記錄開始回 `"JWT expired!"` 的時間點（response interceptor 已確認用這個字串判斷）。
