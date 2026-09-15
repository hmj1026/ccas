# pipeline-progress-throttle Specification

## Purpose
TBD - created by archiving change fix-pipeline-progress-throttle. Update Purpose after archive.
## Requirements
### Requirement: First item progress flushes independently of process uptime

`DbProgressReporter` SHALL flush the first `stage_item_done` call after initialization or `stage_started` regardless of the process monotonic clock value or configured throttle duration.

#### Scenario: Low uptime does not suppress first item

- **WHEN** the monotonic clock is below the configured throttle duration and the reporter receives its first `stage_item_done`
- **THEN** the reporter SHALL execute and commit one progress update

#### Scenario: Rapid subsequent item remains throttled

- **WHEN** the reporter has flushed one item and receives another item within the throttle window
- **THEN** the reporter SHALL suppress the second database update

#### Scenario: New stage resets the first-item window

- **WHEN** `stage_started` completes for a new stage
- **THEN** the next `stage_item_done` SHALL flush immediately
