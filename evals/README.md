# CCAS Eval Fixtures

AI flow evaluation fixtures for the CCAS pipeline.

## Purpose

These evals test the *output quality* of AI-driven pipeline stages — distinct from
`backend/tests/` which test correctness of business logic.

## Structure

```
evals/
  fixtures/      # Sample PDF inputs and expected parse/classify outputs
  results/       # Eval run outputs (gitignored)
  run_evals.py   # Eval runner script
```

## Critical Flows to Cover

| Flow | Priority | Status |
|------|----------|--------|
| PDF parse → transaction rows | P0 | TODO |
| Transaction classify (merchant, category) | P0 | TODO |
| Refund detection (negative amounts) | P1 | TODO |
| Multi-bank statement merge | P1 | TODO |

## Running

```bash
# From repo root
python evals/run_evals.py
```
