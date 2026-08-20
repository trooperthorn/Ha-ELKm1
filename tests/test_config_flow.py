"""Tests for the Elk-M1 config flow: user/manual/serial steps, options,
reconfigure, and reauth.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.elkm1.const import CONF_POLL_INTERVAL, DOMAIN
from custom_components.elkm1.helpers.transport import ConnectionTimeoutError, InvalidAuthError
from custom_components.elkm1.models import ElkPanelData


async def _fake_first_refresh(self) -> None:
    """Stand in for a real connection attempt (sets coordinator.data directly)."""
    self.data = ElkPanelData()


# Patches the coordinator's first refresh for tests that intentionally
# create/reconfigure a real config entry: entry creation schedules a real
# setup as part of finishing the flow, and without this the coordinator
# would actually try to open a network connection (slow, and blocked by
# pytest-socket in this sandbox) rather than exercising the flow logic
# these tests are actually about. __init__.py reads coordinator.data.
# panel_version right after the refresh, so the fake still has to set
# coordinator.data to something real rather than skipping it outright.
_PATCH_COORDINATOR_SETUP = patch(
    "custom_components.elkm1.coordinator.ElkDataUpdateCoordinator.async_config_entry_first_refresh",
    _fake_first_refresh,
)


async def test_user_step_shows_form_with_manual_options(hass):
    """The initial user step lists at least the manual network/serial options."""
    with patch(
        "custom_components.elkm1.config_flow.async_discover_devices",
        AsyncMock(return_value=[]),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    options = result["data_schema"].schema[next(iter(result["data_schema"].schema))].container
    assert "manual_network_flow" in options
    assert "serial_port_flow" in options


async def test_manual_connection_success(hass):
    """A valid manual network connection creates a config entry."""
    with (
        patch(
            "custom_components.elkm1.config_flow.validate_network_connection",
            AsyncMock(return_value=None),
        ),
        _PATCH_COORDINATOR_SETUP,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "manual_network_flow"}
        )
        assert result["step_id"] == "manual_connection"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "address": "1.2.3.4",
                "username": "admin",
                "password": "secret",
                "prefix": "",
                "protocol": "secure",
            },
        )

    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "elks://1.2.3.4"


async def test_manual_connection_cannot_connect(hass):
    """A connection failure surfaces cannot_connect, not a crash."""
    with patch(
        "custom_components.elkm1.config_flow.validate_network_connection",
        AsyncMock(side_effect=ConnectionTimeoutError("timed out")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "manual_network_flow"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "address": "1.2.3.4",
                "username": "admin",
                "password": "secret",
                "prefix": "",
                "protocol": "secure",
            },
        )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


async def test_manual_connection_invalid_auth(hass):
    """Bad credentials surface invalid_auth on the password field."""
    with patch(
        "custom_components.elkm1.config_flow.validate_network_connection",
        AsyncMock(side_effect=InvalidAuthError("rejected")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "manual_network_flow"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "address": "1.2.3.4",
                "username": "admin",
                "password": "wrong",
                "prefix": "",
                "protocol": "secure",
            },
        )

    assert result["type"] == "form"
    assert result["errors"]["password"] == "invalid_auth"


async def test_serial_step_success(hass):
    """A verified serial port creates a config entry."""
    with (
        patch(
            "custom_components.elkm1.config_flow.probe_serial_port",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.elkm1.config_flow.get_persistent_port_path",
            side_effect=lambda p: p,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "serial_port_flow"}
        )
        assert result["step_id"] == "serial"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "serial_port": "/dev/ttyUSB0",
                "prefix": "elkm1",
                "pin": "",
                "verify_device": True,
            },
        )

    assert result["type"] == "create_entry"
    assert result["data"]["serial_port"] == "/dev/ttyUSB0"


async def test_serial_step_cannot_connect(hass):
    """A serial port that doesn't respond surfaces cannot_connect."""
    with (
        patch(
            "custom_components.elkm1.config_flow.probe_serial_port",
            AsyncMock(return_value=False),
        ),
        patch(
            "custom_components.elkm1.config_flow.get_persistent_port_path",
            side_effect=lambda p: p,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "serial_port_flow"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "serial_port": "/dev/ttyUSB99",
                "prefix": "elkm1",
                "pin": "",
                "verify_device": True,
            },
        )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


async def test_options_flow_sets_poll_interval(hass, mock_network_entry):
    """The options flow persists a custom poll_interval."""
    mock_network_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_network_entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 60}
    )
    assert result["type"] == "create_entry"
    assert mock_network_entry.options[CONF_POLL_INTERVAL] == 60


async def test_reconfigure_network_flow(hass, mock_network_entry):
    """Reconfiguring a network entry updates its data and reloads."""
    mock_network_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.elkm1.config_flow.validate_network_connection",
            AsyncMock(return_value=None),
        ),
        _PATCH_COORDINATOR_SETUP,
    ):
        result = await mock_network_entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "address": "5.6.7.8",
                "username": "newuser",
                "password": "newpass",
                "protocol": "secure",
            },
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert mock_network_entry.data["host"] == "elks://5.6.7.8"
    assert mock_network_entry.data["username"] == "newuser"


async def test_reconfigure_serial_flow(hass, mock_serial_entry):
    """Reconfiguring a serial entry updates its serial_port and reloads."""
    mock_serial_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.elkm1.config_flow.probe_serial_port",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.elkm1.config_flow.get_persistent_port_path",
            side_effect=lambda p: p,
        ),
    ):
        result = await mock_serial_entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure_serial"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"serial_port": "/dev/ttyUSB1", "prefix": "elkm1", "pin": ""},
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert mock_serial_entry.data["serial_port"] == "/dev/ttyUSB1"


async def test_reauth_flow_network(hass, mock_network_entry):
    """Reauth on a network entry accepts new credentials and reloads."""
    mock_network_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.elkm1.config_flow.validate_network_connection",
            AsyncMock(return_value=None),
        ),
        _PATCH_COORDINATOR_SETUP,
    ):
        result = await mock_network_entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "newuser", "password": "newpass"}
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert mock_network_entry.data["username"] == "newuser"


async def test_reauth_flow_serial_unsupported(hass, mock_serial_entry):
    """Reauth on a serial entry (no credentials) aborts instead of showing a broken form."""
    mock_serial_entry.add_to_hass(hass)

    result = await mock_serial_entry.start_reauth_flow(hass)

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_unsupported"


@pytest.mark.parametrize(
    ("exc", "expected_error_key"),
    [
        (ConnectionTimeoutError("timeout"), "base"),
        (InvalidAuthError("bad creds"), "password"),
    ],
)
async def test_reconfigure_network_errors(hass, mock_network_entry, exc, expected_error_key):
    """Reconfigure surfaces the same error mapping as the initial connection step."""
    mock_network_entry.add_to_hass(hass)

    with patch(
        "custom_components.elkm1.config_flow.validate_network_connection",
        AsyncMock(side_effect=exc),
    ):
        result = await mock_network_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "address": "5.6.7.8",
                "username": "newuser",
                "password": "newpass",
                "protocol": "secure",
            },
        )

    assert result["type"] == "form"
    assert expected_error_key in result["errors"]
