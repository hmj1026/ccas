# Project Memory Index

> Durable project knowledge lives in the auto-memory system at:
> `~/.claude/projects/-Users-paul-Project-ccas/memory/`
>
> See `MEMORY.md` in that directory for the full index.

## Active Entries

| File | Topic |
|------|-------|
| `user_profile.md` | Paul 的角色背景 |
| `feedback_conventions.md` | 精簡回應、結尾不加摘要 |
| `gotchas_dev_env.md` | Docker anon volume、pnpm、Vite dynamic import 地雷 |
| `gotchas_backend_testing.md` | Secure cookie、to_thread mock、MagicMock Settings 地雷 |
| `gotchas_harness_config.md` | settings.local.json 覆寫、gitnexus FTS 鎖 |
| `refund_policy.md` | 退款為負數金額（非 bug） |
| `defensive_only_findings.md` | 2026-06 稽核純防禦項目清單 |
| `release_process.md` | tag master、changelog=GitHub Releases |

## Key Project Facts

- **Stack**: Python FastAPI + SQLAlchemy async + Alembic + Telegram bot
- **Pipeline**: Gmail PDF → decrypt → parse → classify → REST API / Telegram
- **Banks**: 中信 Sinopac、富邦 Fubon、玉山 E.Sun 等（見 `parser-development.md`）
- **Branch**: develop（main = master）
