# Repository Guidelines

## Project Structure & Module Organization
This repository is organized around OpenSpec workflows rather than application source code. `openspec/config.yaml` defines the active workflow schema. Put in-progress work under `openspec/changes/<kebab-case-name>/`, archived work under `openspec/changes/archive/`, and accepted specs under `openspec/specs/`. Assistant-specific automation is mirrored across `.claude/commands/opsx/*.md`, `.gemini/commands/opsx/*.toml`, and the matching `openspec-*` skill folders in `.claude/skills/`, `.codex/skills/`, and `.gemini/skills/`.

## Build, Test, and Development Commands
Use the OpenSpec CLI as the primary development interface:

- `openspec new change <name>` creates a new change scaffold.
- `openspec status --change <name>` shows artifact progress for a change.
- `openspec instructions <artifact> --change <name>` prints the next artifact template or apply instructions.
- `openspec validate --all --strict` validates all changes and specs before review.
- `openspec archive <name> -y` archives a completed change and updates main specs.
- `openspec schema validate <name>` checks custom project-local schemas when you modify workflow templates.

## Coding Style & Naming Conventions
Keep changes small and mirror existing file formats. Use kebab-case for change names, command names, and new workflow files, for example `add-user-auth`. Preserve the current Markdown-first style in command and skill docs: short headings, direct instructions, and fenced command examples. When you update one assistant surface, keep the equivalent Claude, Codex, and Gemini files aligned unless the platform format requires a deliberate difference.

## Testing Guidelines
There is no application test suite in this repository yet. Validation is workflow-focused: run `openspec validate --all --strict` for broad coverage, or validate the affected item before opening a PR. When editing schemas or templates, also verify the generated instructions manually with `openspec status` and `openspec instructions`.

## Commit & Pull Request Guidelines
Git history currently contains only `Initial commit`, so follow that lead with short, imperative commit subjects such as `Add opsx sync command` or `Update archive workflow docs`. PRs should explain the workflow change, list the mirrored directories touched, and note the validation commands you ran. Include terminal snippets or rendered doc excerpts when behavior or output format changed.
