# Tasks — research-fubon-web-fetch-pipeline

本 change 為純研究，所有任務都是「調查 + 記錄」；無 production code 變更。

## 1. Gmail 端 trace

- [x] 1.1 找出富邦帳單信 message_id（樣本：`19d7301fd0fa5191`，2026-04 帳單）
- [x] 1.2 用 `ccas.ingestor.gmail_client._extract_html_body` 取得原始 HTML
- [x] 1.3 列出所有指向 `fbmbill.taipeifubon.com.tw` 的 `<a href>`（找到 2 個，都導向同一 SPA）

## 2. HTTP flow trace

- [x] 2.1 `curl -v` 第一次 GET，記錄 302 redirect + Set-Cookie（JSESSIONID + NSC_...）
- [x] 2.2 跟 redirect 取得 SPA shell HTML，確認 `#app` 是 Vue 掛載點
- [x] 2.3 抓 `chunk-vendors.js` + `app.js` + `src_views_Login_index_vue.js`
- [x] 2.4 從 `app.js` 靜態分析列出所有 `req()` 呼叫（27 個 endpoint）

## 3. Login payload schema

- [x] 3.1 找到 `const login = data => req('post', 'doLogin', data)`
- [x] 3.2 在 `Login/index.vue` chunk 找到 payload 欄位：`{id, birthday, serialKey, captchaCode}`
- [x] 3.3 確認 `captchaCode` 格式為 `\`${serverToken},${userInput}\``
- [x] 3.4 確認 `serialKey` 從 URL `?code=<hash>` 讀取，即郵件連結的 hash
- [x] 3.5 確認 birthday 格式為民國 7 碼（`0850101`）
- [x] 3.6 確認 `Authorization` header 由 axios interceptor 加入（raw jwt，無 `Bearer ` 前綴）

## 4. Captcha flow

- [x] 4.1 確認 endpoint `GET checkImgs/captcha.jpg`
- [x] 4.2 發現 response body 非二進位，而是 `<server_token>,<base64_jpeg>` 純文字
- [x] 4.3 在 Login chunk 找到 NOSESSION 版註解（`//20251022 NOSESSION版 - 前端自帶 key`）
- [x] 4.4 解出 JPEG 規格：125×55、5 位 → **實測為 4 位**數字、藍字 + 紅斜線

## 5. Captcha 辨識 POC

- [x] 5.1 抓 10 張真實 captcha 樣本
- [x] 5.2 目視標注 ground truth
- [x] 5.3 Tesseract + HSV 前處理：實測 4/10（40%）
- [x] 5.4 Tesseract + contour per-digit：實測 0/10（segmentation 失敗）
- [x] 5.5 EasyOCR raw：實測 5/10（50%）
- [x] 5.6 EasyOCR + 前處理：實測 0/10（前處理毀掉 pretrained 特徵）
- [x] 5.7 分析 confidence 分布，確認 `conf≥0.80 && len==4` gate 能 100% 切開對錯
- [x] 5.8 計算 retry 數學：7 retry → 99.2%

## 6. PDF download endpoint

- [x] 6.1 確認 `/client/pdf/<hash>` 也是 SPA 入口（Content-Type: text/html）
- [x] 6.2 從 app.js route 表找到 `/setting/downloadPDF` 對應 `src_views_Setting_DownloadPDF_index_vue`
- [ ] 6.3 抓該 chunk 取得實際 download endpoint — **延後到 impl change**（需實際登入後測試）

## 7. 文件產出

- [x] 7.1 撰寫 `proposal.md`（WHY + capabilities + impact）
- [x] 7.2 撰寫 `design.md`（完整 trace + decision matrix + 架構建議 + ADRs + open questions）
- [x] 7.3 撰寫 `tasks.md`（本檔案）
- [x] 7.4 更新 `docs/e2e-user-guide-walkthrough.md` 問題追蹤表 #8 狀態為 `research-done`

## 8. 不做的事（明確交接給 impl change）

- [ ] 8.1 實際寫 `client.py` / `captcha.py` / `flow.py` → 由 `impl-fubon-fetcher-pipeline` 做
- [ ] 8.2 加 `easyocr` 到 `pyproject.toml` → 由 impl change 做
- [ ] 8.3 加 `FUBON_ID_NUMBER` / `FUBON_BIRTHDAY` 到 `Settings` → 由 impl change 做
- [ ] 8.4 Dockerfile 烘 easyocr 權重 → 由 impl change 做
- [ ] 8.5 `docs/user-guide.md` 加免責聲明 → 由 impl change 做
