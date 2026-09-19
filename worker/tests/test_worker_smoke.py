"""Smoke tests for Worker."""

from app.main import get_worker_status


def test_worker_status_returns_ready():
    """Verify worker status returns ready and proper service name."""
    status = get_worker_status()
    assert status["status"] == "ready"
    assert status["service"] == "worker"
    assert "environment" in status
