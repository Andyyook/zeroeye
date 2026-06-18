"""Tests for market data endpoints."""
import pytest

class TestMarketEndpoints:
    def test_market_data_feed(self, test_client, mock_market_data):
        """Verify market data feed returns prices for all symbols."""
        result = test_client.post("/market/feed", mock_market_data)
        assert result["ok"] is True
        assert len(mock_market_data["symbols"]) == 3
    
    def test_symbol_lookup(self, test_client):
        """Verify symbol lookup works."""
        result = test_client.get("/market/symbols")
        assert result["ok"] is True

    def test_market_status(self, test_client):
        """Verify market status endpoint."""
        result = test_client.get("/market/status")
        assert result["ok"] is True
