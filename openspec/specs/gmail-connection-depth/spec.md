# gmail-connection-depth Specification

## Purpose
TBD - created by archiving change deepen-codebase-architecture. Update Purpose after archive.
## Requirements
### Requirement: Gmail connection state has one owner

The Gmail connection module SHALL own the state transitions for credentials upload, authorization, callback success, callback error, connected status, polling completion, and revoke. The frontend page and backend route SHALL not maintain competing interpretations of the same connection state.

#### Scenario: Upload enables authorization

- **WHEN** a valid `credentials.json` is uploaded
- **THEN** the connection outcome SHALL indicate that authorization is available and SHALL preserve the existing upload response behavior

#### Scenario: Callback success reaches connected

- **WHEN** Google returns a valid authorization code and state
- **THEN** the connection module SHALL persist the token through its storage adapter, report connected status, and allow the page polling to stop

#### Scenario: Callback error is actionable

- **WHEN** Google returns an OAuth error, an expired state, or a redirect URI mismatch
- **THEN** the connection module SHALL produce the existing actionable error outcome and SHALL not report the connection as connected

#### Scenario: Revoke returns to disconnected

- **WHEN** the user revokes Gmail access
- **THEN** the connection module SHALL perform the existing best-effort remote revoke and local token removal, then report disconnected status

### Requirement: Credential source policy is centralized and secret-safe

The credential policy SHALL use encrypted DB value before environment fallback before none for bank login credentials. A DB row with a master-key mismatch SHALL raise the existing ingestion error; HTTP responses and status views SHALL never expose plaintext or ciphertext.

#### Scenario: DB value overrides environment

- **WHEN** both an encrypted DB row and an environment value exist for the same bank credential
- **THEN** the effective source SHALL be DB and the resolved value SHALL be the decrypted DB value

#### Scenario: Environment fallback remains available

- **WHEN** no DB row exists and the corresponding environment value is configured
- **THEN** the effective source SHALL be environment and ingestion SHALL receive that value

#### Scenario: Decryption mismatch is not hidden

- **WHEN** a DB row exists but the active master key cannot decrypt it
- **THEN** the credential policy SHALL raise the existing ingestion error and SHALL not silently fall back to environment

### Requirement: External systems are replaceable adapters

The Gmail connection module SHALL isolate Google OAuth calls, token encryption/storage, credential file access, credential source access, and HTTP response translation behind replaceable adapters. The page rendering adapter SHALL consume connection outcomes rather than reconstructing OAuth policy.

#### Scenario: In-memory adapters exercise the flow

- **WHEN** tests supply in-memory Google, storage, credential, and HTTP adapters
- **THEN** they SHALL verify the complete connection state transition without network access or filesystem writes

#### Scenario: Production adapters preserve existing contracts

- **WHEN** the production adapters are used
- **THEN** endpoint paths, redirect behavior, response envelopes, token permissions, and existing polling semantics SHALL remain unchanged

