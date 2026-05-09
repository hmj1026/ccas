#!/usr/bin/env bash
# Fetch Telegram chat IDs from recent bot updates.
# Usage: ./scripts/get-telegram-chat-id.sh [BOT_TOKEN]
#   If BOT_TOKEN is omitted, reads TELEGRAM_BOT_TOKEN from .env

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

fail() {
  printf '\n[ERROR] %s\n' "$1" >&2
  exit 1
}

# --- Check jq ---
command -v jq >/dev/null 2>&1 || fail "需要 jq。請先安裝：brew install jq / apt-get install jq"

# --- Resolve token ---
if [[ -n "${1:-}" ]]; then
  TOKEN="$1"
else
  if [[ ! -f "$ENV_FILE" ]]; then
    fail "找不到 $ENV_FILE，且未提供 BOT_TOKEN 參數。用法：$0 [BOT_TOKEN]"
  fi
  TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  TOKEN="${TOKEN//\"/}"  # strip quotes
  TOKEN="${TOKEN//\'/}"
  if [[ -z "$TOKEN" ]]; then
    fail "TELEGRAM_BOT_TOKEN 未設定於 $ENV_FILE，且未提供參數。"
  fi
fi

# --- Call getUpdates ---
printf '正在查詢 Telegram Bot API...\n'

response=$(curl -sf "https://api.telegram.org/bot${TOKEN}/getUpdates" 2>&1) || {
  # Check if it's an auth error
  if echo "$response" | jq -e '.ok == false' >/dev/null 2>&1; then
    desc=$(echo "$response" | jq -r '.description // "unknown error"')
    fail "Telegram API 錯誤：$desc"
  fi
  fail "無法連線 Telegram API。請確認網路連線及 bot token 是否正確。"
}

api_ok=$(echo "$response" | jq -r '.ok')
if [[ "$api_ok" != "true" ]]; then
  desc=$(echo "$response" | jq -r '.description // "unknown error"')
  fail "Telegram API 錯誤：$desc"
fi

# --- Extract unique chats ---
chats=$(echo "$response" | jq -r '
  [.result[] | (.message.chat // .channel_post.chat // .edited_message.chat // .callback_query.message.chat // empty)]
  | unique_by(.id)
  | .[]
  | "\(.id)\t\(.type)\t\(.title // .first_name // "N/A")"
')

if [[ -z "$chats" ]]; then
  printf '\n找不到最近的訊息。\n'
  printf '請先對 bot 傳送任意訊息（私訊或加入群組後在群組內傳訊息），然後重新執行此腳本。\n'
  printf '\n注意：若 bot 服務正在執行中（docker compose up），getUpdates 會被 webhook 攔截。\n'
  printf '請先停止 bot 服務（docker compose stop bot），再重新執行。\n'
  printf '\n替代方式：在 Telegram 中對 @userinfobot 或 @RawDataBot 傳送訊息可取得 chat ID。\n'
  exit 0
fi

# --- Print results ---
printf '\n找到以下聊天室：\n\n'
printf '  %-20s %-14s %s\n' "Chat ID" "類型" "名稱"
printf '  %-20s %-14s %s\n' "-------" "----" "----"

while IFS=$'\t' read -r id type name; do
  printf '  %-20s %-14s %s\n' "$id" "$type" "$name"
done <<< "$chats"

printf '\n將 Chat ID 填入 .env：\n'
printf '  TELEGRAM_CHAT_ID=<上方 Chat ID>          # Pipeline 通知目標\n'
printf '  TELEGRAM_ALLOWED_CHAT_IDS=<逗號分隔>     # Bot 指令白名單\n'
printf '\n提示：群組 Chat ID 為負數（例如 -1001234567890）。\n'
printf '若需多個白名單，用逗號分隔：TELEGRAM_ALLOWED_CHAT_IDS=123,-1001234567890\n'
