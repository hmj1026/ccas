# Gemini CLI Project Context: OpenSpec Assistant Configuration

This project manages "OpenSpec" workflows and related AI assistant configurations for Claude, Codex, and Gemini. It is a **Non-Code Project** focused on spec-driven development and workflow automation.

## Project Overview
OpenSpec is an AI-native system for spec-driven development. This repository contains:
- `openspec/`: Core specifications, change proposals, and active workflow configurations.
- `.gemini/`, `.claude/`, `.codex/`: AI assistant-specific commands and skills.
- `AGENTS.md`: Foundational guidelines for AI agents (take precedence over general defaults).

## Key Development Commands
Use the `openspec` CLI for all workflow-related tasks.

| Task | Command |
| :--- | :--- |
| **New Change** | `openspec new change <kebab-case-name>` |
| **Check Progress** | `openspec status --change <name>` |
| **Get Instructions** | `openspec instructions <artifact> --change <name>` |
| **Validate All** | `openspec validate --all --strict` |
| **Archive Change** | `openspec archive <name> -y` |

## Gemini-Specific Workflows
This repository includes a set of specialized commands and skills for the Gemini CLI under the `opsx` namespace.

### Available Slash Commands
- `/opsx:new`: Start a new change using the experimental artifact workflow.
- `/opsx:continue`: Continue working on an existing change.
- `/opsx:apply`: Implement tasks from a change.
- `/opsx:verify`: Verify implementation matches change artifacts.
- `/opsx:archive`: Archive a completed change.
- `/opsx:onboard`: Guided onboarding for OpenSpec.
- `/opsx:explore`: Enter explore mode for brainstorming/investigation.
- `/opsx:ff`: Fast-forward through artifact creation.
- `/opsx:sync`: Sync delta specs from a change to main specs.
- `/opsx:bulk-archive`: Archive multiple completed changes at once.

### Specialized Skills
Activate these skills for expert guidance on OpenSpec workflows:
- `openspec-new-change`
- `openspec-continue-change`
- `openspec-apply-change`
- `openspec-verify-change`
- `openspec-archive-change`
- `openspec-onboard`
- `openspec-explore`
- `openspec-ff-change`
- `openspec-sync-specs`
- `openspec-bulk-archive-change`

## Development Conventions
1. **Naming:** Use `kebab-case` for change names, command names, and new workflow files (e.g., `add-user-auth`).
2. **Organization:**
   - Active changes: `openspec/changes/<name>/`
   - Accepted specs: `openspec/specs/`
   - Archived work: `openspec/changes/archive/`
3. **Synchronization:** When updating assistant configurations, ensure `.gemini/`, `.claude/`, and `.codex/` remain aligned.
4. **Validation:** Always run `openspec validate --all --strict` before finalizing changes to schemas or specs.
5. **Commit Messages:** Use short, imperative subjects (e.g., `Add opsx sync command`).

## Testing & Validation
Validation is workflow-focused. Run `openspec validate --all --strict` for broad coverage. When editing schemas or templates, verify generated instructions with `openspec status` and `openspec instructions`.
