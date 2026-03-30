# CCAS Implementation Execution Order

## Dependency Graph

```
Phase 1: foundation-setup
    |
Phase 2: gmail-ingestor
    |
Phase 3: pdf-decryptor
    |
Phase 4: parser-engine
    |
Phase 5: keyword-classifier
    |
    +--- Phase 6a: telegram-bot      (parallel)
    +--- Phase 6b: backend-api       (parallel)
              |
    +--- Phase 7:  frontend-dashboard
    +--- Phase 7*: pipeline-scheduler (parallel with 7)
    |
Phase 8: integration-polish
```

## Phase Details

| Phase | Change | Tasks | Prerequisites | Notes |
|-------|--------|------:|---------------|-------|
| 1 | `foundation-setup` | 42 | None | Greenfield scaffold: backend, frontend, DB, Docker |
| 2 | `gmail-ingestor` | 19 | Phase 1 | Gmail API auth, PDF download, staging table |
| 3 | `pdf-decryptor` | 18 | Phase 2 | pikepdf decrypt, per-bank password from env |
| 4 | `parser-engine` | 14 | Phase 3 | Versioned parser registry, Bill + Transaction writes |
| 5 | `keyword-classifier` | 11 | Phase 4 | Keyword rules from DB, longest-match wins |
| 6a | `telegram-bot` | 19 | Phases 4, 5 | Commands, bill actions, proactive notifications |
| 6b | `backend-api` | 16 | Phases 4, 5 | REST API + Bearer auth for React dashboard |
| 7 | `frontend-dashboard` | 13 | Phase 6b | React + Vite + Tailwind + shadcn/ui, 5 pages |
| 7* | `pipeline-scheduler` | 24 | Phases 2-6 | RQ jobs, retry logic, payment reminders |
| 8 | `integration-polish` | 22 | All | E2E tests, exception hierarchy, structured logging |

**Total: 198 tasks across 10 changes**

## Parallelization

- **Phase 6a + 6b**: `telegram-bot` and `backend-api` are independent. Both depend on `parser-engine` + `keyword-classifier` but not on each other.
- **Phase 7 + 7***: `frontend-dashboard` only needs `backend-api`. `pipeline-scheduler` needs all pipeline stages (2-5) + `telegram-bot` for notifications. These can overlap once their respective deps are done.

## Data Flow

```
Gmail --> staged PDF --> decrypted PDF --> Bill + Transaction[] --> categorized Transaction
                                                |                         |
                                                v                         v
                                          REST API -----------------> React Dashboard
                                                |
                                                v
                                         Telegram Bot <-- payment reminders
```

## Staging Status Machine

Defined across changes 2-4, used by change 7*:

```
staged --> decrypted --> parsed       (success path)
  |           |
  v           v
(skipped)  decrypt_failed
              |
              v
           parse_failed
              |
              v
        manual_review_needed    (after 3 RQ retries exhausted)
```

## Progress Tracker

- [ ] Phase 1: foundation-setup
- [ ] Phase 2: gmail-ingestor
- [ ] Phase 3: pdf-decryptor
- [ ] Phase 4: parser-engine
- [ ] Phase 5: keyword-classifier
- [ ] Phase 6a: telegram-bot
- [ ] Phase 6b: backend-api
- [ ] Phase 7: frontend-dashboard
- [ ] Phase 7*: pipeline-scheduler
- [ ] Phase 8: integration-polish
