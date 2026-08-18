# tests/conftest.py
# Ensures the Home Assistant testing plugins and 'hass' fixture are properly loaded

"""Global fixtures for Elk-M1 integration tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for testing."""
    yield


@pytest.fixture
def mock_elk_connection():
    """Mock ElkM1Connection for tests."""
    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    return mock
