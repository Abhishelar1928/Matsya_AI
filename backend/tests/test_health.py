"""
MatsyaAI Maharashtra — Health Endpoint Tests.

Verifies the /api/v1/health endpoint returns the expected structure.
Database connectivity is not required for the endpoint to respond.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_200() -> None:
    """GET /api/v1/health should return 200 with status fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "database" in data
    assert "timestamp" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_root_endpoint_returns_200() -> None:
    """GET / should return 200 with app metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200

    data = response.json()
    assert data["app"] == "MatsyaAI Maharashtra"
    assert "docs" in data
    assert "health" in data
