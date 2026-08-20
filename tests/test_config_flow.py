"""Test config flow."""
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.elkm1.const import DOMAIN


# You can remove @pytest.mark.asyncio if you added asyncio_mode = auto to pytest.ini
async def test_config_flow_user_step_with_discovery(hass: HomeAssistant) -> None:
    """Test user step with auto-discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"

# Patch the exact location where your config_flow.py imports or calls the connection object
@patch("custom_components.elkm1.config_flow.ElkM1Connection")
async def test_config_flow_connection_error(mock_elk_class, hass: HomeAssistant) -> None:
    """Test handling of connection errors."""

    # Configure the mock to simulate a failed connection
    mock_instance = mock_elk_class.return_value
    # Assuming your connect() method returns a boolean or raises an exception:
    mock_instance.connect.return_value = False
    # Or if it raises an error: mock_instance.connect.side_effect = ConnectionError()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"serial_port": "/dev/ttyUSB99"},  # The mock will now intercept this
    )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"
