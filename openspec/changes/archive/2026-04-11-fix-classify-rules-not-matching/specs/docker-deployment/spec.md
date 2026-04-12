## ADDED Requirements

### Requirement: Automatic categories seeding on backend startup

The system SHALL seed the `categories` table from `/config/categories.yaml` during backend container startup, immediately after the `bank_configs` seed step and before uvicorn starts serving requests. The seed step MUST be idempotent and MUST fast-fail with non-zero exit on failure.

#### Scenario: Fresh container seeds categories

- **WHEN** a clean `docker compose up -d backend` runs against an empty database
- **THEN** the entrypoint SHALL execute `uv run python -m ccas.tools.categories --apply` after `bank_configs --apply`, the tool SHALL report `created=N` matching the YAML row count, and uvicorn SHALL start successfully afterwards

#### Scenario: Restart is idempotent

- **WHEN** a backend container that has already seeded categories is restarted without changing `categories.yaml`
- **THEN** the entrypoint categories step SHALL report `created=0 updated=0 unchanged=N` and SHALL NOT raise

#### Scenario: Seed failure aborts startup

- **WHEN** the categories seed step exits with non-zero status
- **THEN** `docker-entrypoint.sh` SHALL exit non-zero without `exec`-ing uvicorn
