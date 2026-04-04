# Skill 選用策略

## 優先順序（多 skill 同時命中時依序選擇）

1. **OpenSpec 類**（new/continue/apply/verify/sync/archive）— 觸發詞：「建立變更」「新功能 spec」「archive」「同步規格」
2. **bug-investigation** — 觸發詞：「調查」「trace」「為什麼」「排查」「找原因」「root cause」
3. **tdd-guide** agent（功能或 bugfix 且需調整測試）— 注意：此為 ECC agent，非 local skill
4. **software-architecture** — 觸發詞：「架構」「跨模組設計」「重構方向」「系統設計」
5. **其他 ECC skill**（python-patterns、backend-patterns、api-design 等）— 最小必要集合

## 原則

- **因必要而用，不因可用而用**：有相關 skill 不代表必須啟動
- **小型變更直接實作**：不套完整流程型 skill（避免過度儀式化）
- **execution-policy 優先**：透過任務分類路由後，以 execution-policy 的 agent 流程為準，不再重複觸發本優先順序
- **同名 skill 以專案內版本為準**：若本地 `.claude/skills/` 有同名版本，優先於全域 ECC skill

> 強制後置步驟規則詳見 `execution-policy.md`。
> 完整 ECC Agent 列表見 `CLAUDE.md`。
