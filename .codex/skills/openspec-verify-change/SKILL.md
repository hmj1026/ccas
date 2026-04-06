---
name: openspec-verify-change
description: Verify implementation matches change artifacts. Use when the user wants to validate that implementation is complete, correct, and coherent before archiving.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

Verify that an implementation matches the change artifacts (specs, tasks, design).

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `openspec list --json` to get available changes. Use the **AskUserQuestion tool** to let the user select.

   Show changes that have implementation tasks (tasks artifact exists).
   Include the schema used for each change if available.
   Mark changes with incomplete tasks as "(In Progress)".

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Check status to understand the schema**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - Which artifacts exist for this change

3. **Get the change directory and load artifacts**

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   This returns the change directory and context files. Read all available artifacts from `contextFiles`.

4. **Initialize verification report structure**

   Create a report structure with three dimensions:
   - **Completeness**: Track tasks and spec coverage
   - **Correctness**: Track requirement implementation and scenario coverage
   - **Coherence**: Track design adherence and pattern consistency

   Each dimension can have CRITICAL, WARNING, or SUGGESTION issues.

5. **Verify Completeness**

   **Task Completion**:
   - If tasks.md exists in contextFiles, read it
   - Parse checkboxes: `- [ ]` (incomplete) vs `- [x]` (complete)
   - Count complete vs total tasks
   - If incomplete tasks exist:
     - Add CRITICAL issue for each incomplete task
     - Recommendation: "Complete task: <description>" or "Mark as done if already implemented"

   **Spec Coverage**:
   - If delta specs exist in `openspec/changes/<name>/specs/`:
     - Extract all requirements (marked with "### Requirement:")
     - For each requirement:
       - Search codebase for keywords related to the requirement
       - Assess if implementation likely exists
     - If requirements appear unimplemented:
       - Add CRITICAL issue: "Requirement not found: <requirement name>"
       - Recommendation: "Implement requirement X: <description>"

6. **Verify Correctness**

   **Requirement Implementation Mapping**:
   - For each requirement from delta specs:
     - Search codebase for implementation evidence
     - If found, note file paths and line ranges
     - Assess if implementation matches requirement intent
     - If divergence detected:
       - Add WARNING: "Implementation may diverge from spec: <details>"
       - Recommendation: "Review <file>:<lines> against requirement X"

   **Scenario Coverage**:
   - For each scenario in delta specs (marked with "#### Scenario:"):
     - Check if conditions are handled in code
     - Check if tests exist covering the scenario
     - If scenario appears uncovered:
       - Add WARNING: "Scenario not covered: <scenario name>"
       - Recommendation: "Add test or implementation for scenario: <description>"

7. **Verify Coherence**

   **Design Adherence**:
   - If design.md exists in contextFiles:
     - Extract key decisions (look for sections like "Decision:", "Approach:", "Architecture:")
     - Verify implementation follows those decisions
     - If contradiction detected:
       - Add WARNING: "Design decision not followed: <decision>"
       - Recommendation: "Update implementation or revise design.md to match reality"
   - If no design.md: Skip design adherence check, note "No design.md to verify against"

   **Code Pattern Consistency**:
   - Review new code for consistency with project patterns
   - Check file naming, directory structure, coding style
   - If significant deviations found:
     - Add SUGGESTION: "Code pattern deviation: <details>"
     - Recommendation: "Consider following project pattern: <example>"

8. **Verify Archive Readiness (Spec Sync Pre-check)**

   For each delta spec in `openspec/changes/<name>/specs/*/spec.md`:

   a. **Read delta spec** — identify sections (`## ADDED Requirements`, `## MODIFIED Requirements`, etc.) and extract requirement headers under each section.

   b. **Read corresponding main spec** at `openspec/specs/<capability>/spec.md` (may not exist). Extract existing requirement headers.

   c. **Check operation/header consistency:**

      - **MODIFIED but header missing in main spec**: The delta marks a requirement as MODIFIED, but `### Requirement: <name>` does not exist in the main spec. This means the delta should use ADDED instead.
        → Add CRITICAL: "Delta spec `<capability>` marks '<requirement>' as MODIFIED, but it does not exist in main spec. Change to ADDED."

      - **ADDED but header already exists in main spec**: The delta marks a requirement as ADDED, but `### Requirement: <name>` already exists in the main spec. This could indicate a previous failed archive that partially wrote the main spec without rolling back.
        → Add CRITICAL: "Delta spec `<capability>` marks '<requirement>' as ADDED, but it already exists in main spec. Either delete the stale main spec entry (if from a failed archive) or change to MODIFIED."

   d. **Validate delta spec requirements format:**

      For each `### Requirement:` block in the delta spec:
      - Check body contains `SHALL` or `MUST` keyword → CRITICAL if missing: "Requirement '<name>' in delta spec lacks SHALL/MUST keyword"
      - Check at least one `#### Scenario:` exists under it → CRITICAL if missing: "Requirement '<name>' in delta spec has no scenarios"
      - Check each scenario has `**WHEN**` and `**THEN**` → WARNING if missing

   e. **Validate main spec requirements format (pre-merge check):**

      For each existing `### Requirement:` block in the main spec (if it exists):
      - Check body contains `SHALL` or `MUST` keyword → WARNING if missing: "Main spec `<capability>` requirement '<name>' lacks SHALL/MUST — archive validation will fail"
      - Check at least one `#### Scenario:` exists → WARNING if missing: "Main spec `<capability>` requirement '<name>' has no scenarios — archive validation will fail"

      This catches pre-existing main spec issues that would cause the merged result to fail validation.

   f. **Check for orphaned main specs from partial syncs:**

      If `openspec/specs/<capability>/spec.md` contains "TBD - created by archiving change <name>" in the Purpose section, but the change is still active (not archived), this indicates a previous failed archive left a stale file.
      → Add WARNING: "Main spec `<capability>` appears to be a stale artifact from a previous failed archive of this change"

9. **Generate Verification Report**

   **Summary Scorecard**:
   ```
   ## Verification Report: <change-name>

   ### Summary
   | Dimension         | Status           |
   |-------------------|------------------|
   | Completeness      | X/Y tasks, N reqs|
   | Correctness       | M/N reqs covered |
   | Coherence         | Followed/Issues  |
   | Archive Readiness | Sync OK/Issues   |
   ```

   **Issues by Priority**:

   1. **CRITICAL** (Must fix before archive):
      - Incomplete tasks
      - Missing requirement implementations
      - Each with specific, actionable recommendation

   2. **WARNING** (Should fix):
      - Spec/design divergences
      - Missing scenario coverage
      - Each with specific recommendation

   3. **SUGGESTION** (Nice to fix):
      - Pattern inconsistencies
      - Minor improvements
      - Each with specific recommendation

   **Final Assessment**:
   - If CRITICAL issues: "X critical issue(s) found. Fix before archiving."
   - If only warnings: "No critical issues. Y warning(s) to consider. Ready for archive (with noted improvements)."
   - If all clear: "All checks passed. Ready for archive."

**Verification Heuristics**

- **Completeness**: Focus on objective checklist items (checkboxes, requirements list)
- **Correctness**: Use keyword search, file path analysis, reasonable inference - don't require perfect certainty
- **Coherence**: Look for glaring inconsistencies, don't nitpick style
- **False Positives**: When uncertain, prefer SUGGESTION over WARNING, WARNING over CRITICAL
- **Actionability**: Every issue must have a specific recommendation with file/line references where applicable

**Graceful Degradation**

- If only tasks.md exists: verify task completion only, skip spec/design checks
- If tasks + specs exist: verify completeness and correctness, skip design
- If full artifacts: verify all three dimensions
- Always note which checks were skipped and why

**Output Format**

Use clear markdown with:
- Table for summary scorecard
- Grouped lists for issues (CRITICAL/WARNING/SUGGESTION)
- Code references in format: `file.ts:123`
- Specific, actionable recommendations
- No vague suggestions like "consider reviewing"
