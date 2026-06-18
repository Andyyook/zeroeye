"""Tests for configuration endpoints."""
import pytest

class TestConfigEndpoints:
    def test_config_retrieval(self, test_client):
        """Verify config retrieval."""
        result = test_client.get("/config")
        assert result["ok"] is True

    def test_config_update(self, test_client):
        """Verify config update."""
        updates = {"risk_limit": 5000, "max_leverage": 50}
        result = test_client.post("/config/update", updates)
        assert result["ok"] is True
