# harness-doc-accuracy Specification

## Purpose
TBD - created by archiving change fix-harness-doc-drift. Update Purpose after archive.
## Requirements
### Requirement: skills 目錄不得含死 symlink（F1）
`.claude/skills/` 目錄 SHALL 不包含任何指向不存在目標的 symlink；CLAUDE.md 的 skill 來源描述 SHALL 與檔案系統實況一致（`.agents/` 已不存在時不得宣稱其為來源）。

#### Scenario: 死 symlink 清除完畢
- **WHEN** 執行 `find .claude/skills -type l ! -exec test -e {} \; -print | wc -l`
- **THEN** 輸出為 `0`（稽核時為 193）

#### Scenario: CLAUDE.md 不再宣稱 .agents/skills 為來源
- **WHEN** 執行 `test -d .agents || ! grep -q '.agents/skills' CLAUDE.md`
- **THEN** 條件成立（`.agents/` 不存在時 CLAUDE.md 無該宣稱）

### Requirement: CLAUDE.md 不得引用不存在的 skill（F2）
CLAUDE.md SHALL 只引用檔案系統或已安裝 plugin 中實際存在的 skill；不存在的 `ccas-dev-commands`/`ccas-env-config`/`ccas-qa-acceptance`/`ccas-tech-stack` 引用 SHALL 被移除（除非改為補建該 skill）。

#### Scenario: 幽靈 skill 引用已移除
- **WHEN** 執行 `git grep -ln 'ccas-dev-commands\|ccas-env-config\|ccas-qa-acceptance\|ccas-tech-stack' -- CLAUDE.md`
- **THEN** 輸出為空（稽核時四者皆命中 CLAUDE.md）

### Requirement: CLAUDE.md 不得寫死 GitNexus 統計數字（F3）
CLAUDE.md 的 GitNexus 段落 SHALL 不含具體 symbols/relationships/flows 數字（避免每次重建索引即漂移）；GitNexus 索引 SHALL 跟上 HEAD。

#### Scenario: 寫死數字已移除
- **WHEN** 執行 `grep -c '12114\|21142' CLAUDE.md`
- **THEN** 輸出為 `0`

#### Scenario: 索引新鮮
- **WHEN** 執行 `test "$(jq -r .lastCommit .gitnexus/meta.json)" = "$(git rev-parse HEAD)" && echo FRESH || echo STALE`
- **THEN** 輸出為 `FRESH`（稽核時為 STALE）

### Requirement: 無強制機制的規則不得標示 MUST（F4）
CLAUDE.md 對 `gitnexus_impact`/`gitnexus_detect_changes` 的要求 SHALL 使用與實際強制力一致的措辭：無 hook gate 時不得使用「MUST」，改為建議性措辭。

#### Scenario: MUST 措辭已降級
- **WHEN** 執行 `grep -c 'MUST run impact analysis\|MUST run .gitnexus_detect_changes' CLAUDE.md`
- **THEN** 輸出為 `0`

### Requirement: 外部 plugin 依賴須明文標注（F5）
`.claude/rules/execution-policy.md` SHALL 明文標注 sentinel 驅動 review（`.pending-review` 等）由外部 dhpk plugin 提供，repo 自身 hooks 不寫入 sentinel。

#### Scenario: 依賴標注存在
- **WHEN** 執行 `grep -l 'dhpk plugin' .claude/rules/execution-policy.md`
- **THEN** 命中該檔（稽核時 `grep -rln 'pending-review' .claude/hooks .claude/settings.json` 為空，證明 repo 不自帶）

### Requirement: dhpk verified range 須涵蓋實際運行版本（F6）
`.claude/dhpk-versions.json` 的 verified range SHALL 涵蓋當前 session 實際運行的 dhpk 版本（稽核時運行 0.20.1，verified 上限僅 0.19.x）。

#### Scenario: verified range 涵蓋運行版本
- **WHEN** 新 session 啟動並執行 `jq -r '.verified[].range' .claude/dhpk-versions.json`
- **THEN** SessionStart 的 dhpk version advisory 不再標示 `(unverified)`，且 verified range 包含當前運行版本（升級至 0.23.x 或補驗 0.20.x 皆可；注意 2026-07-02 已有並行 session 在工作區加入 0.23.x 條目，收斂後為準）

### Requirement: 最終複審須限縮範圍（P1）
stop-review 觸發的最終 code-review SHALL 限縮為增量範圍（僅本回合變更檔案），避免長時間全量複審（session log 中 2 次遭使用者中止）。此慣例 SHALL 記載於 rules。

#### Scenario: 複審範圍慣例已記載
- **WHEN** 執行 `grep -c '增量\|incremental' .claude/rules/execution-policy.md`
- **THEN** 輸出 `≥1`

### Requirement: harness 不得寫死過期 context 上限（P2）
harness 文件與腳本 SHALL 不含與實際模型不符的寫死 context 上限常數（如 200k，實際為 1M）；若清查後不存在，記錄清查結果即可。排除範圍：`.claude/dhpk-versions.json` 的歷史驗證註記（如 0.16.x 條目提及「200k Sonnet 4.6」屬當時事實紀錄，非活性常數，不列入）。

#### Scenario: 無過期 context 常數
- **WHEN** 執行 `grep -rn '200k\|200,000\|200_000' CLAUDE.md .claude/rules/ .claude/hooks/ 2>/dev/null | grep -iv 'coverage' | wc -l`
- **THEN** 輸出為 `0`

### Requirement: 需脈絡決策優先文字確認（P3）
對需要完整脈絡的決策（如 tag/release 時機），模型 SHALL 優先給出建議並以文字確認，而非 AskUserQuestion 選單（session log 中 1 次選單遭打斷改打字）。此慣例 SHALL 記載於 rules 或 CLAUDE.md。

#### Scenario: 決策確認慣例已記載
- **WHEN** 執行 `grep -rl '建議+文字確認' .claude/rules/ CLAUDE.md`
- **THEN** 至少命中一檔（實作前為空 — 該詞組為本 change 新增的慣例描述）

