# pipeline-lifecycle-depth Specification

## Purpose
TBD - created by archiving change deepen-codebase-architecture. Update Purpose after archive.
## Requirements
### Requirement: Pipeline run lifecycle has one outcome authority

The system SHALL have one Pipeline run module responsible for aggregating stage summaries, classifying a run outcome, and producing the terminal `PipelineRun` status. Queue adapters and stage implementations MUST NOT independently reconstruct the same failure policy.

#### Scenario: Non-notify stage error fails the run

- **WHEN** ingest, decrypt, parse, or classify produces a stage error or classify produces an all-or-nothing failure summary
- **THEN** the Pipeline run module SHALL produce a failed terminal outcome with a useful error message

#### Scenario: Notify remains best effort

- **WHEN** the notify stage has an item failure but all data stages complete without failure
- **THEN** the Pipeline run module SHALL preserve the existing best-effort behavior and SHALL NOT mark the data run failed solely because of that notify item failure

#### Scenario: Unexpected worker exception fails the run

- **WHEN** the stage execution raises an unexpected exception before a structured summary is returned
- **THEN** the lifecycle adapter SHALL persist `failed`, `error_message`, and `completed_at` before re-raising for queue retry semantics

### Requirement: Lifecycle summary is the shared progress and status source

The Pipeline run module SHALL derive progress snapshots, stage summaries, failure details, and terminal status from the same lifecycle result. The worker, operations polling path, CLI summary path, and scheduler path SHALL not require separate failure interpretation.

#### Scenario: Stage completion updates one summary

- **WHEN** a stage completes with counts, errors, and elapsed time
- **THEN** the lifecycle result SHALL expose the same values to progress persistence and the returned pipeline summary

#### Scenario: Empty stage remains observable

- **WHEN** a selected stage has zero items
- **THEN** the lifecycle result SHALL record a completed stage with zero counts and SHALL not leave the operations view stuck in that stage

### Requirement: Lifecycle seam is substitutable in tests

The Pipeline run module SHALL expose a narrow interface suitable for an in-memory lifecycle adapter. Tests SHALL be able to verify status and progress policy without starting RQ or opening a production database session.

#### Scenario: In-memory lifecycle verifies failure policy

- **WHEN** a test supplies an in-memory lifecycle adapter and a structured stage summary containing a parse error
- **THEN** the test SHALL observe the same failed outcome that the production persistence adapter would record

#### Scenario: Existing callers retain stage execution behavior

- **WHEN** CLI, scheduler, or worker invokes the pipeline with its existing options and notify binding
- **THEN** stage order, stage range validation, summary shape, and retry behavior SHALL remain unchanged

