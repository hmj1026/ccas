## ADDED Requirements

### Requirement: Centralized settings via pydantic-settings
The system SHALL define a `Settings` class using pydantic-settings that loads configuration from environment variables and `.env` files. The Settings class SHALL include: `database_url` (default: "sqlite:///data/ccas.db"), `telegram_bot_token` (required), `telegram_chat_id` (required), `gmail_credentials_path` (default: "/data/credentials.json"), `gmail_token_path` (default: "/data/token.json"), `log_level` (default: "INFO"), `api_host` (default: "0.0.0.0"), `api_port` (default: 8000).

#### Scenario: Settings load from environment
- **WHEN** environment variable `TELEGRAM_BOT_TOKEN=abc123` is set and Settings is instantiated
- **THEN** `settings.telegram_bot_token` equals `"abc123"`

#### Scenario: Settings load from .env file
- **WHEN** a `.env` file contains `TELEGRAM_BOT_TOKEN=abc123` and Settings is instantiated
- **THEN** `settings.telegram_bot_token` equals `"abc123"`

#### Scenario: Missing required setting raises error
- **WHEN** `TELEGRAM_BOT_TOKEN` is not set in environment or .env
- **THEN** Settings instantiation raises a ValidationError with a clear message

#### Scenario: Default values applied
- **WHEN** `DATABASE_URL` is not set
- **THEN** `settings.database_url` equals `"sqlite:///data/ccas.db"`

### Requirement: Environment example file
The system SHALL include a `.env.example` file in the `backend/` directory with all configuration keys and placeholder values, serving as documentation for required settings.

#### Scenario: Example file lists all keys
- **WHEN** a developer reads `backend/.env.example`
- **THEN** all keys from the Settings class are listed with descriptive placeholder values

### Requirement: Settings singleton access
The system SHALL provide a `get_settings()` function that returns a cached Settings instance, usable as a FastAPI dependency.

#### Scenario: Settings reused across requests
- **WHEN** `get_settings()` is called multiple times
- **THEN** the same Settings instance is returned each time (no re-parsing)
