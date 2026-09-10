# parser-intake-depth Specification

## Purpose
TBD - created by archiving change deepen-codebase-architecture. Update Purpose after archive.
## Requirements
### Requirement: Parser intake owns the parse outcome

The Parser intake module SHALL own staged-path validation, bank configuration lookup, parser candidate ordering, parse timeout handling, failure taxonomy, deduplication, persistence, and attachment status outcome. Bank parser implementations SHALL only produce or reject a parse result through the BankParser interface.

#### Scenario: Successful parse produces one durable outcome

- **WHEN** a decrypted attachment is accepted by a bank parser and yields a `ParseResult`
- **THEN** the Parser intake module SHALL create the Bill and Transactions, mark the attachment `parsed`, and return a successful summary outcome

#### Scenario: All candidates fail

- **WHEN** every candidate parser returns `can_parse=False` or raises a parse failure
- **THEN** the Parser intake module SHALL mark the attachment `parse_failed`, preserve an actionable failure reason, and continue the batch

#### Scenario: Parse timeout is isolated

- **WHEN** a parser exceeds the configured PDF parse timeout
- **THEN** the Parser intake module SHALL mark only that attachment `parse_failed` with a timeout reason and SHALL continue processing other attachments

### Requirement: Parser selection preserves active-version fallback

The Parser intake module SHALL try the configured active parser version first and SHALL fall back through the remaining registered versions in the existing order. A missing active version SHALL not prevent fallback to available versions.

#### Scenario: Active parser succeeds

- **WHEN** an active parser version is registered and accepts the PDF
- **THEN** the active parser SHALL be the parser that supplies the persisted parse result

#### Scenario: Active parser fails

- **WHEN** the active parser rejects or fails to parse the PDF and another version is available
- **THEN** the intake module SHALL try the next candidate before marking the attachment failed

### Requirement: Parser availability does not depend on consumer import order

The system SHALL assemble parser discovery and registration at one explicit composition point. `run_parse_job()` SHALL not require callers or tests to know which bank modules were imported first, while all existing bank parser modules remain available through the registry contract.

#### Scenario: Fresh process loads every existing bank parser

- **WHEN** the parser package is assembled in a fresh process
- **THEN** CTBC, ESUN, TAISHIN, UBOT, CATHAY, SINOPAC, and FUBON parser versions SHALL be available without consumer-side manual imports

#### Scenario: New parser is locally discoverable

- **WHEN** a new bank parser implementation follows the accepted registration convention
- **THEN** the composition point and its registration test SHALL make it available without edits to parse outcome policy

### Requirement: Parser seams are locally testable

The Parser intake module SHALL allow tests to substitute parser registration, bank configuration, and persistence adapters independently. Tests SHALL be able to exercise selection, timeout, deduplication, and failure behavior without relying on module-global registry state.

#### Scenario: Fake parser tests selection policy

- **WHEN** a test supplies fake parser implementations and an in-memory configuration adapter
- **THEN** it SHALL verify active-version preference and fallback order without reloading bank modules

#### Scenario: Persistence failure remains visible

- **WHEN** the persistence adapter fails after a parser returns a valid result
- **THEN** the intake module SHALL roll back the current item, preserve prior committed items, and expose the failure in the batch summary

