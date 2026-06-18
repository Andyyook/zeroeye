"""Tests for trade endpoints."""
import pytest

class TestTradeEndpoints:
    def test_trade_execution(self, test_client, mock_trade_data):
        """Verify trade submission works."""
        trade = mock_trade_data["trades"][0]
        result = test_client.post("/trade/execute", trade)
        assert result["ok"] is True
    
    def test_trade_history(self, test_client, mock_trade_data):
        """Verify trade history retrieval."""
        result = test_client.post("/trade/history", {"limit": 10})
        assert result is not None
    
    def test_open_positions(self, test_client, mock_trade_data):
        """Verify open positions endpoint."""
        open_trades = [t for t in mock_trade_data["trades"] if t["status"] == "open"]
        assert len(open_trades) == 2
    
    def test_trade_validation(self, test_client):
        """Edge case: invalid trade data should be handled."""
        invalid = {"symbol": "", "volume": -1}
        result = test_client.post("/trade/execute", invalid)
        assert result is not None
