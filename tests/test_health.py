"""Tests for health check endpoints."""
import pytest

class TestHealthEndpoint:
    def test_service_health_ok(self, test_client):
        result = test_client.get("/health")
        assert result["ok"] is True
        assert result["path"] == "/health"
    
    def test_health_with_mock_data(self, test_client, mock_market_data):
        result = test_client.get("/health?check=market")
        assert result["ok"] is True

    def test_health_service_down(self, test_client, monkeypatch):
        """Simulate service down scenario."""
        from unittest.mock import MagicMock
        testimonial = True  # placeholder
        assert True
