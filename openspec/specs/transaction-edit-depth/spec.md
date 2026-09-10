# transaction-edit-depth Specification

## Purpose
TBD - created by archiving change deepen-codebase-architecture. Update Purpose after archive.
## Requirements
### Requirement: Transaction edit behavior has one owner

The Transaction edit module SHALL own note and merchant-alias drafts, category and tag mutations, manual-override reset, save status, debounce timing, query cache update, and failure recovery. The page SHALL render the module outcome and forward user intent without duplicating commit policy.

#### Scenario: Category edit commits the existing contract

- **WHEN** the user selects a different category
- **THEN** the edit module SHALL issue the existing partial update, update the detail cache from the response, and expose the updated detail

#### Scenario: Tags commit the normalized list

- **WHEN** the user adds or removes a tag
- **THEN** the edit module SHALL reject empty or duplicate additions, submit the normalized tag list through the existing update contract, and update the detail cache on success

#### Scenario: Note and alias use debounce with blur flush

- **WHEN** the user changes note or merchant alias and the debounce interval elapses
- **THEN** the edit module SHALL commit one update; when the field loses focus before the interval elapses, it SHALL flush the pending value immediately

#### Scenario: Manual override reset preserves metadata

- **WHEN** the user resets a manual category override
- **THEN** the edit module SHALL call the existing reset contract, update the detail cache, and preserve note, tags, and merchant alias

### Requirement: Edit failure is observable and recoverable

The Transaction edit module SHALL expose saving, saved, idle, and error outcomes. A failed mutation SHALL not silently discard the user-visible error, and the page SHALL retain its existing retry/refetch behavior.

#### Scenario: Auto-save failure returns to idle with error

- **WHEN** a debounced note or alias update fails
- **THEN** the module SHALL expose an error outcome, stop the saving indicator, and leave the page able to refetch the server detail

#### Scenario: Mutation response becomes the cache source

- **WHEN** a category, tag, alias, note, or reset mutation succeeds
- **THEN** the module SHALL use the returned detail as the cache value rather than requiring a second request for the same mutation

### Requirement: Edit seams are testable without page rendering

The Transaction edit module SHALL expose a narrow interface suitable for an in-memory request and cache adapter. Tests SHALL be able to verify draft transitions, debounce, commit, failure, and cache behavior without mounting the complete route page.

#### Scenario: In-memory adapter verifies debounce

- **WHEN** a test supplies a fake request adapter and advances the debounce clock
- **THEN** it SHALL observe exactly one update with the final draft value

#### Scenario: Page integration preserves accessibility states

- **WHEN** the rendering adapter consumes the edit module outcomes
- **THEN** loading, error, saved, retry, and field accessibility states SHALL remain available to the existing frontend tests

