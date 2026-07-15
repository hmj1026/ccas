# ccas gh cli 無法正確推送 commit 調查紀錄

## 問題描述
- **預期行為**：可以使用 `git push`（或經由相關 CLI、GitHub CLI `gh`）正常將 commit 推送到遠端倉庫。
- **實際行為**：推送時出錯，報錯訊息主要包含兩個部分：
  1. `fatal: failed to get: -25308` (Keychain 存取拒絕)。
  2. `ERROR: Claude plugin marketplace 'openai-codex' has drifted` (Pre-push hook 攔截)。
- **樣本資料**：
  - 本地分支 `develop` 領先 `origin/develop` 1 個提交。
  - Git remote 網址為 `https://github.com/hmj1026/ccas.git`。
  - 本地 `credential.helper` 全域或系統級設定為 `osxkeychain`。
  - 本地 `.claude/plugin-pins.json` 的 `openai-codex` 預期版本為 `80c31f99`，但本地實際為 `db52e28f`。

## 調查進度
- [x] Phase 1: 問題釐清
- [x] Phase 2: 證據蒐集
- [x] Phase 3: 根因分析
- [ ] Phase 4: 修正方案設計
- [ ] Phase 5: 知識文件化

## 證據蒐集與測試
1. **執行 `git push --dry-run` 輸出：**
   ```
   fatal: failed to get: -25308
   fatal: failed to store: -25308
   === Claude Plugin Pin Check ===
   ERROR: Claude plugin marketplace 'openai-codex' has drifted
          Expected: 80c31f99570876c3ef40327838b0a2ca1ae2cd9c
          Actual:   db52e28f4d9ded852ab3942cea316258ae4ef346
   ```
2. **Keychain 狀態：**
   - 系統設定的 `credential.helper` 為 `osxkeychain`（位於 `/opt/homebrew/etc/gitconfig`）。
   - 在非互動式 (non-interactive) 或 sandbox 環境下，嘗試存取 Keychain 會因為缺乏權限或未解鎖而拋出 macOS Keychain 錯誤 `-25308` (`errSecInteractionNotAllowed`)。
3. **Plugin Drift 狀態：**
   - 讀取 `.claude/plugin-pins.json` 發現 `openai-codex` 被鎖定在 `80c31f99570876c3ef40327838b0a2ca1ae2cd9c`，而本地 `~/.claude/plugins/marketplaces/openai-codex` 的實際 commit 為 `db52e28f4d9ded852ab3942cea316258ae4ef346`。

## 根因分析
1. **憑證讀取失敗 (Keychain -25308)**：
   - Git 的 credential helper 預設為 `osxkeychain`。在 IDE、背景執行程序或 sandbox 環境中，Git 沒有權限或無法開啟 GUI 提示來存取 macOS Keychain，導致認證中斷。
2. **推送被 pre-push hook 拒絕**：
   - 專案的 `scripts/pre-push.sh` 會呼叫 `verify-claude-plugins.sh` 檢查本地 plugin 是否與 `plugin-pins.json` 的版本一致。由於 `openai-codex` 版本發生偏移 (drifted)，檢查腳本以 exit code 1 退出，從而阻止了 push。

## 阻礙與缺口
- 暫無。接下來進入 Phase 4，設計修正方案。

