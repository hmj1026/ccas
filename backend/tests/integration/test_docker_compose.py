"""Docker Compose 配置完整性測試。

驗證 docker-compose.yaml 包含必要的服務定義。
直接解析 YAML 以避免依賴 .env 或 Docker daemon。
"""

from pathlib import Path

import pytest
import yaml


def _load_compose() -> dict:
    """讀取並解析 docker-compose.yaml。"""
    compose_path = Path(__file__).resolve().parents[3] / "docker-compose.yaml"
    if not compose_path.exists():
        pytest.skip(f"docker-compose.yaml not found at {compose_path}")
    return yaml.safe_load(compose_path.read_text())


class TestDockerComposeWorker:
    """驗證 worker 服務定義存在於 Docker Compose 配置。"""

    def test_worker_service_defined(self):
        """docker-compose.yaml 應包含 worker 服務。"""
        config = _load_compose()
        assert "worker" in config["services"]

    def test_worker_depends_on_backend_and_redis(self):
        """worker 服務應依賴 backend 與 redis。"""
        config = _load_compose()
        worker = config["services"]["worker"]
        depends_on = worker.get("depends_on", {})
        assert "backend" in depends_on
        assert "redis" in depends_on

    def test_worker_uses_rq_command(self):
        """worker 服務的 command 應包含 rq worker。"""
        config = _load_compose()
        worker = config["services"]["worker"]
        command = worker.get("command", [])
        assert "rq" in command
        assert "worker" in command

    def test_worker_restart_policy(self):
        """worker 服務應設定 restart: unless-stopped。"""
        config = _load_compose()
        worker = config["services"]["worker"]
        assert worker.get("restart") == "unless-stopped"
