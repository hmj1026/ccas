#!/bin/bash
# CCAS Skill Platform Parity Check
# Reminds to sync .claude/skills/ changes to .codex/ and .gemini/ platforms

FILE="$1"

# Only trigger for .claude/skills/*/SKILL.md
[[ "$FILE" == *".claude/skills/"*"/SKILL.md" ]] || exit 0

SKILL_NAME=$(echo "$FILE" | sed 's|.*\.claude/skills/||' | sed 's|/SKILL.md||')

echo ""
echo "[skill-sync] 偵測到 .claude/skills/$SKILL_NAME/SKILL.md 修改"
echo "[skill-sync] 請確認同步以下平台定義："
echo "  .codex/skills/$SKILL_NAME/SKILL.md"
echo "  .gemini/skills/$SKILL_NAME/SKILL.md"
echo ""
