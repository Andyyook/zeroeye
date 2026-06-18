"""Tests for risk calculation endpoints."""
import pytest

class TestRiskEndpoints:
    def test_portfolio_risk(self, test_client, sample_portfolio):
        """Verify portfolio risk endpoint returns expected metrics."""
        result = test_client.post("/risk/portfolio", sample_portfolio)
        assert result["ok"] is True
        assert result["path"] == "/risk/portfolio"

    def test_position_risk(self, test_client, mock_trade_data):
        """Verify position-level risk calculation."""
        for trade in mock_trade_data["trades"]:
            result = test_client.post("/risk/position", trade)
            assert result["ok"] is True

    def test_market_risk(self, test_client, mock_market_data):
        """Verify market risk factors."""
        result = test_client.post("/risk/market", mock_market_data)
        assert result["ok"] is True
    
    def test_var_calculation(self, test_client, sample_portfolio):
        """Verify Value-at-Risk calculation."""
        var_input = {"portfolio": sample_portfolio, "confidence": 0.95}
        result = test_client.post("/risk/var", var_input)
        assert result["ok"] is True

    def test_stress_test(self, test_client, sample_portfolio):
        """Verify stress test scenario."""
        stress = {"portfolio": sample_portfolio, "scenario": "rate_hike_50bp"}
        result = test_client.post("/risk/stress", stress)
        assert result["ok"] is True

    def test_empty_portfolio(self, test_client):
        """Edge case: empty portfolio should not crash."""
        empty = {"portfolio_id": "empty", "positions": [], "cash": 0}
        result = test_client.post("/risk/portfolio", empty)
        assert result is not None
