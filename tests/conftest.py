"""Shared test fixtures and configuration for backend API tests."""
import json, os
import pytest

@pytest.fixture
def test_client():
    """Provide a test client for API integration tests."""
    class TestClient:
        def __init__(self):
            self.base_url = os.environ.get("API_BASE_URL", "http://localhost:8080")
            self.headers = {"Content-Type": "application/json"}
        
        def get(self, path: str):
            """Simulate a GET request. In unit tests, mock this."""
            return {"ok": True, "path": path, "method": "GET"}
        
        def post(self, path: str, data: dict):
            """Simulate a POST request."""
            return {"ok": True, "path": path, "method": "POST", "body": data}
    
    return TestClient()

@pytest.fixture
def auth_token():
    """Provide a mock authentication token."""
    return "test-token-for-api-tests"

@pytest.fixture
def mock_market_data():
    """Realistic market data for risk calculation tests."""
    return {
        "symbols": ["EURUSD", "XAUUSD", "GBPUSD"],
        "prices": {"EURUSD": 1.0850, "XAUUSD": 2350.00, "GBPUSD": 1.2650},
        "timestamp": "2026-06-18T10:00:00Z",
    }

@pytest.fixture
def mock_trade_data():
    """Sample trade data for endpoint tests."""
    return {
        "trades": [
            {"id": 1, "symbol": "EURUSD", "direction": "buy", "volume": 0.1, "price": 1.0840, "status": "open"},
            {"id": 2, "symbol": "XAUUSD", "direction": "sell", "volume": 0.05, "price": 2355.00, "status": "closed"},
            {"id": 3, "symbol": "GBPUSD", "direction": "buy", "volume": 0.2, "price": 1.2640, "status": "open"},
        ]
    }

@pytest.fixture
def sample_portfolio():
    """Sample portfolio for risk endpoint tests."""
    return {
        "portfolio_id": "port-001",
        "total_value": 100000.00,
        "cash": 25000.00,
        "positions": [
            {"symbol": "EURUSD", "volume": 1.0, "unrealized_pnl": 120.50},
            {"symbol": "XAUUSD", "volume": 0.5, "unrealized_pnl": -45.00},
        ],
        "risk_metrics": {"var_95": 1500.00, "var_99": 2800.00, "sharpe": 1.2},
    }
