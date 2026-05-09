## ADDED Requirements

### Requirement: Bank config volume mount

The system SHALL mount the host `./config/` directory into backend, worker, scheduler, and bot containers as read-only at `/config`, so that `banks.yaml` and `bank-code-registry.yaml` are available inside the container without rebuilding the image.

#### Scenario: Backend container can read bank config

- **WHEN** `docker compose up -d backend` completes
- **THEN** `docker exec ccas-backend-1 ls /config/banks.yaml /config/bank-code-registry.yaml` SHALL return both files with exit code 0

#### Scenario: Config mount is read-only

- **WHEN** the backend container attempts to write to `/config/banks.yaml`
- **THEN** the write SHALL fail with a read-only filesystem error

#### Scenario: All pipeline-relevant services receive the mount

- **WHEN** `docker compose config` is rendered
- **THEN** the `backend`, `worker`, `scheduler`, and `bot` services SHALL each include `./config:/config:ro` in their `volumes`; the `frontend` and `redis` services SHALL NOT include it

### Requirement: Automatic bank_configs seeding on backend startup

The system SHALL seed the `bank_configs` table from `/config/banks.yaml` and `/config/bank-code-registry.yaml` during backend container startup, after database migrations have been applied and before uvicorn starts serving requests. The seed step MUST be idempotent — unchanged rows SHALL NOT be rewritten on subsequent restarts.

#### Scenario: Fresh container seeds from empty table

- **WHEN** a clean `docker compose up -d backend` runs against an empty database
- **THEN** the entrypoint SHALL execute `uv run python -m ccas.tools.bank_configs --apply`, the tool SHALL report `created=N` where N matches the number of enabled banks in `banks.yaml`, and uvicorn SHALL start successfully afterwards

#### Scenario: Restart after seed is idempotent

- **WHEN** a backend container that has already seeded `bank_configs` is restarted without changing `banks.yaml`
- **THEN** the entrypoint seed step SHALL report `created=0 updated=0 unchanged=N` and SHALL NOT raise

#### Scenario: Seed failure aborts startup

- **WHEN** the bank_configs seed step exits with a non-zero status (e.g. malformed YAML, DB unreachable)
- **THEN** `docker-entrypoint.sh` SHALL exit non-zero without `exec`-ing uvicorn, and the container SHALL be marked unhealthy by Compose

#### Scenario: Pipeline ingest succeeds immediately after first startup

- **WHEN** an operator runs `docker compose up -d` on a fresh clone followed by `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --to ingest`
- **THEN** the pipeline SHALL NOT raise `未找到任何啟用的銀行設定` and the ingest stage SHALL proceed past bank-config validation

### Requirement: BANK_CONFIG_DIR environment variable overrides CLI defaults

The `ccas.tools.bank_configs` CLI SHALL honor the `BANK_CONFIG_DIR` environment variable as the source of default paths for `--config` and `--registry`. Explicit `--config` / `--registry` flags MUST still take precedence over the environment variable, and the environment variable MUST take precedence over the hard-coded `../config/...` defaults.

#### Scenario: Env var sets defaults inside container

- **WHEN** `BANK_CONFIG_DIR=/config` is set and `uv run python -m ccas.tools.bank_configs --apply` is invoked with no path flags
- **THEN** the tool SHALL read `/config/banks.yaml` and `/config/bank-code-registry.yaml`

#### Scenario: Explicit flag overrides env var

- **WHEN** `BANK_CONFIG_DIR=/config` is set and the tool is invoked as `--config /tmp/custom-banks.yaml --registry /tmp/custom-registry.yaml --apply`
- **THEN** the tool SHALL read from the `/tmp/custom-*` paths and ignore `BANK_CONFIG_DIR`

#### Scenario: Host fallback when env var unset

- **WHEN** `BANK_CONFIG_DIR` is unset (as in `scripts/setup.sh` host flow)
- **THEN** the tool SHALL fall back to the hard-coded `../config/banks.yaml` and `../config/bank-code-registry.yaml` defaults relative to the backend working directory
