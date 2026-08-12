"""Pytest fixtures for Elk-M1 integration tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = AsyncMock()
    coordinator.data = {...}
    coordinator.last_update_success = True
    return coordinator

@pytest.fixture
async def hass_mock():
    """Create mock Home Assistant instance."""
    hass = AsyncMock()
    hass.bus = MagicMock()
    hass.data = {}
    return hass
