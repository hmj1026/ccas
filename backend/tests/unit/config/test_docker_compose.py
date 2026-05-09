"""Verify docker-compose.yaml matches user-guide §6 service definitions.

Parses YAML only — does not start containers.
"""

from pathlib import Path

import pytest
import yaml

_COMPOSE_PATH = Path(__file__).resolve().parents[4] / "docker-compose.yaml"

EXPECTED_SERVICES = {"backend", "worker", "scheduler", "bot", "frontend", "redis"}


@pytest.fixture(scope="module")
def compose():
    if not _COMPOSE_PATH.exists():
        pytest.skip(f"docker-compose.yaml not found at {_COMPOSE_PATH}")
    return yaml.safe_load(_COMPOSE_PATH.read_text())


class TestDockerComposeServices:
    def test_all_six_services_defined(self, compose):
        actual = set(compose["services"]) & EXPECTED_SERVICES
        assert actual == EXPECTED_SERVICES

    def test_backend_port_8000(self, compose):
        ports = compose["services"]["backend"]["ports"]
        assert any("8000" in p for p in ports)

    def test_frontend_port_8080(self, compose):
        ports = compose["services"]["frontend"]["ports"]
        assert any("8080" in p for p in ports)

    def test_redis_port_6379(self, compose):
        ports = compose["services"]["redis"]["ports"]
        assert any("6379" in p for p in ports)

    def test_backend_healthcheck_defined(self, compose):
        assert "healthcheck" in compose["services"]["backend"]

    def test_backend_target_production(self, compose):
        assert compose["services"]["backend"]["build"]["target"] == "production"

    def test_frontend_target_production(self, compose):
        assert compose["services"]["frontend"]["build"]["target"] == "production"
