"""Test config flow."""
from homeassistant.core import HomeAssistant

from custom_components.elkm1.const import DOMAIN


async def test_config_flow_user_step_with_discovery(hass: HomeAssistant) -> None:
    """Test user step with auto-discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_config_flow_connection_error(hass: HomeAssistant) -> None:
    """Test handling of connection errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"serial_port": "/dev/ttyUSB99"},  # Non-existent port
    )
    
    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"
