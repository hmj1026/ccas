# harness-doc-accuracy Specification

## Purpose

Keep repository documentation aligned with runtime-provided agent tooling and
avoid committing machine-specific harness state or installed skills.

## Requirements

### Requirement: Agent tooling and installed skills are local-only (F1)

The repository SHALL NOT track Agent client directories (`.claude/`, `.codex/`,
`.cursor/`, `.gemini/`, `.agents/`, `.agent/`), the GitNexus index
(`.gitnexus/`), or generated skill lock files (`skills-lock.json`). Project
instructions SHALL remain in versioned root files and `docs/`.

#### Scenario: No local Agent directories are tracked

- **WHEN** executing `git ls-files -- .claude .codex .cursor .gemini .agents .agent .gitnexus skills-lock.json`
- **THEN** the command produces no output

#### Scenario: Local Agent paths are ignored

- **WHEN** executing `for path in .claude/settings.json .codex/skills/example .cursor/rules/example .gemini/skills/example .agents/skills/example .agent/example .gitnexus/meta.json skills-lock.json; do git check-ignore -q -- "$path" || exit 1; done`
- **THEN** the command succeeds for every path

### Requirement: CLAUDE.md does not reference unavailable project skills (F2)

CLAUDE.md SHALL only reference skills supplied by the runtime catalog or
documented project workflows; obsolete `ccas-dev-commands`,
`ccas-env-config`, `ccas-qa-acceptance`, and `ccas-tech-stack` references SHALL
be absent.

#### Scenario: Obsolete skill references are absent

- **WHEN** executing `git grep -n -E 'ccas-dev-commands|ccas-env-config|ccas-qa-acceptance|ccas-tech-stack' -- CLAUDE.md`
- **THEN** the command produces no output

### Requirement: CLAUDE.md does not contain volatile GitNexus statistics (F3)

CLAUDE.md SHALL not contain concrete GitNexus symbol, relationship, or flow
counts that would drift when the index is rebuilt.

#### Scenario: Volatile statistics are absent

- **WHEN** executing `grep -c '12114\|21142' CLAUDE.md`
- **THEN** the output is `0`

### Requirement: Advisory checks are described accurately (F4)

CLAUDE.md SHALL describe `gitnexus_impact` and `gitnexus_detect_changes` as
advisory checks when no repository hook enforces them.

#### Scenario: No false mandatory wording

- **WHEN** executing `grep -c 'MUST run impact analysis\|MUST run .gitnexus_detect_changes' CLAUDE.md`
- **THEN** the output is `0`
