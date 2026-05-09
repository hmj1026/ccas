## MODIFIED Requirements

### Requirement: QA testing guide known limitations accuracy
The QA testing guide (`docs/qa-testing-guide.md`) §已知限制 SHALL accurately reflect the current system capabilities. Each listed limitation MUST be verified against the actual codebase state before publication.

#### Scenario: Bank support count is accurate
- **WHEN** a QA tester reads §已知限制
- **THEN** the document SHALL list all 7 supported banks (CTBC, SINOPAC, ESUN, UBOT, CATHAY, TAISHIN, FUBON) and SHALL NOT claim only CTBC is supported

#### Scenario: Bot test coverage is accurate
- **WHEN** a QA tester reads §已知限制
- **THEN** the document SHALL NOT claim bot handlers have no automated tests, because `tests/unit/bot/test_handlers.py` and `tests/integration/bot/test_handlers.py` exist

#### Scenario: Test count is approximate
- **WHEN** a QA tester reads §自動化測試
- **THEN** the test count SHALL use an approximate figure (e.g., 「1000+」) to reduce maintenance burden

### Requirement: E2E walkthrough issue tracking accuracy
The E2E walkthrough (`docs/e2e-user-guide-walkthrough.md`) issue tracking table SHALL reflect the actual resolution status of each issue.

#### Scenario: Applied issues are archived
- **WHEN** an issue in the tracking table has been fully applied and verified
- **THEN** its status SHALL be updated to `archived`
