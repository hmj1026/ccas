"""Gmail OAuth 授權工具測試。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ccas.storage.oauth_secrets import read_token_payload
from ccas.storage.secrets import MasterKeyManager
from ccas.tools.gmail_auth import (
    AuthPaths,
    GmailAuthSetupError,
    generate_token,
    main,
    resolve_auth_paths,
    should_generate_token,
)


def test_resolve_auth_paths_requires_credentials_file(tmp_path: Path):
    credentials = tmp_path / "missing-credentials.json"
    token = tmp_path / "token.json"

    with pytest.raises(GmailAuthSetupError) as exc:
        resolve_auth_paths(credentials, token)

    message = str(exc.value)
    assert "GMAIL_CREDENTIALS_PATH" in message
    assert str(credentials) in message


def test_resolve_auth_paths_success(tmp_path: Path):
    credentials = tmp_path / "credentials.json"
    token = tmp_path / "token.json"
    credentials.write_text('{"installed": {}}')

    result = resolve_auth_paths(credentials, token)

    assert isinstance(result, AuthPaths)
    assert result.credentials_path == credentials
    assert result.token_path == token


def test_resolve_auth_paths_accepts_string_input(tmp_path: Path):
    credentials = tmp_path / "credentials.json"
    credentials.write_text('{"installed": {}}')

    result = resolve_auth_paths(str(credentials), str(tmp_path / "token.json"))

    assert isinstance(result.credentials_path, Path)
    assert isinstance(result.token_path, Path)


def test_should_generate_token_skips_existing_file_without_force(tmp_path: Path):
    credentials = tmp_path / "credentials.json"
    token = tmp_path / "token.json"
    credentials.write_text('{"installed": {}}')
    token.write_text('{"token": "existing"}')

    paths = resolve_auth_paths(credentials, token)

    assert should_generate_token(paths, force=False) is False
    assert should_generate_token(paths, force=True) is True


@patch("ccas.tools.gmail_auth.get_settings")
@patch("ccas.tools.gmail_auth.InstalledAppFlow")
def test_generate_token_runs_oauth_and_creates_dirs(
    mock_flow_cls: MagicMock, mock_get_settings: MagicMock, tmp_path: Path
):
    credentials = tmp_path / "credentials.json"
    token_dir = tmp_path / "nested" / "dir"
    token = token_dir / "token.json"
    credentials.write_text('{"installed": {}}')

    # Stage 6 A3: the CLI now encrypts token.json at rest. Point the master.key
    # at tmp so the test never writes into the repo's ./data/secrets.
    manager = MasterKeyManager(tmp_path / "secrets" / "master.key")
    mock_get_settings.return_value.master_key_manager = manager

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "new", "refresh_token": "1//secret"}'
    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds
    # CLI now decrypts credentials.json then builds the flow from the dict
    # (security-reviewer M4) rather than from_client_secrets_file.
    mock_flow_cls.from_client_config.return_value = mock_flow

    paths = AuthPaths(credentials_path=credentials, token_path=token)
    result = generate_token(paths)

    assert result == token
    assert token_dir.exists()
    assert token.stat().st_mode & 0o777 == 0o600
    # On disk: encrypted envelope, NOT plaintext refresh_token.
    on_disk = token.read_text(encoding="utf-8")
    assert "1//secret" not in on_disk
    assert json.loads(on_disk)["ccas_enc"] is not None
    # Round-trips through the decrypt read path.
    assert read_token_payload(token, manager)["refresh_token"] == "1//secret"
    # Flow was built from the decrypted credentials dict.
    mock_flow_cls.from_client_config.assert_called_once()
    assert mock_flow_cls.from_client_config.call_args.args[0] == {"installed": {}}
    mock_flow.run_local_server.assert_called_once_with(port=0)


def test_main_returns_2_on_missing_credentials(tmp_path: Path):
    argv = [
        "--credentials",
        str(tmp_path / "nonexistent.json"),
        "--token",
        str(tmp_path / "token.json"),
    ]

    result = main(argv)

    assert result == 2


def test_main_returns_0_when_token_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    credentials = tmp_path / "credentials.json"
    token = tmp_path / "token.json"
    credentials.write_text('{"installed": {}}')
    token.write_text('{"token": "existing"}')

    argv = [
        "--credentials",
        str(credentials),
        "--token",
        str(token),
    ]

    result = main(argv)

    assert result == 0
    assert "[SKIP]" in capsys.readouterr().out
