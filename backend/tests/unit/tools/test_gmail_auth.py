"""Gmail OAuth 授權工具測試。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


@patch("ccas.tools.gmail_auth.InstalledAppFlow")
def test_generate_token_runs_oauth_and_creates_dirs(
    mock_flow_cls: MagicMock, tmp_path: Path
):
    credentials = tmp_path / "credentials.json"
    token_dir = tmp_path / "nested" / "dir"
    token = token_dir / "token.json"
    credentials.write_text('{"installed": {}}')

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "new"}'
    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds
    mock_flow_cls.from_client_secrets_file.return_value = mock_flow

    paths = AuthPaths(credentials_path=credentials, token_path=token)
    result = generate_token(paths)

    assert result == token
    assert token.read_text(encoding="utf-8") == '{"token": "new"}'
    assert token_dir.exists()
    assert token.stat().st_mode & 0o777 == 0o600
    mock_flow_cls.from_client_secrets_file.assert_called_once()
    mock_flow.run_local_server.assert_called_once_with(port=0)


def test_main_returns_2_on_missing_credentials(tmp_path: Path):
    argv = [
        "--credentials", str(tmp_path / "nonexistent.json"),
        "--token", str(tmp_path / "token.json"),
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
        "--credentials", str(credentials),
        "--token", str(token),
    ]

    result = main(argv)

    assert result == 0
    assert "[SKIP]" in capsys.readouterr().out
