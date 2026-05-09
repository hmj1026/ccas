## ADDED Requirements

### Requirement: Cross-platform CJK font fixture for parser integration tests
Parser integration tests SHALL use a shared `cjk_font_path` fixture that resolves CJK font paths across Linux and macOS, skipping tests when no font is available.

#### Scenario: Linux Docker environment with wqy-zenhei
- **WHEN** `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc` exists
- **THEN** the fixture SHALL return that path and all parser integration tests SHALL run

#### Scenario: macOS with system CJK font
- **WHEN** Linux font is absent but `/System/Library/Fonts/STHeiti Medium.ttc` exists
- **THEN** the fixture SHALL return the macOS path and all parser integration tests SHALL run

#### Scenario: No CJK font available
- **WHEN** no candidate CJK font path exists
- **THEN** the fixture SHALL call `pytest.skip()` and tests SHALL be marked as skipped (not failed)
