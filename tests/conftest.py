"""Pytest fixtures for Elk-M1 integration tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_elk_connection():
    """Mock ElkM1Connection for tests."""
    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    return mock
