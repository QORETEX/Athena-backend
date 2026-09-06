"""
Tests for health check endpoint
"""
import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Test basic health check endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_check_models_status(client: TestClient):
    """Test health check includes model status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "models_loaded" in data
    # Models may not be loaded in test environment, that's ok


@pytest.mark.asyncio
async def test_health_check_performance(client: TestClient):
    """Test health check responds quickly."""
    import time

    start = time.time()
    response = client.get("/health")
    duration = time.time() - start

    assert response.status_code == 200
    assert duration < 1.0  # Should respond in under 1 second
