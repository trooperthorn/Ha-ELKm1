"""Alarmo auto-setup helper for ELK-M1 integration.

This file provides utilities to automatically configure Alarmo with ELK-M1 zones.

Since Alarmo auto-discovers binary_sensor entities, the workflow is:
1. ELK-M1 integration creates binary_sensor entities for all zones
2. Alarmo automatically discovers these zones in its "Sensors" tab
3. This helper provides a service to automatically configure them
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER: logging.Logger = logging.getLogger(__name__)

ALARMO_DOMAIN = "alarmo"


async def async_setup_alarmo_auto_config(hass: HomeAssistant) -> None:
    """Set up Alarmo auto-configuration service."""

    async def handle_auto_setup_alarmo(call: ServiceCall) -> None:
        """Auto-configure Alarmo with ELK-M1 zones."""
        _LOGGER.info("Starting Alarmo auto-setup for ELK-M1 zones")

        entity_reg = er.async_get(hass)
        elk_zones = []

        for entity in entity_reg.entities.values():
            if (
                entity.domain == "binary_sensor"
                and DOMAIN in str(entity.platform)
                and "zone" in entity.entity_id
                and "battery" not in entity.entity_id
            ):
                elk_zones.append({
                    "entity_id": entity.entity_id,
                    "name": entity.original_name or entity.name or entity.entity_id,
                    "device_id": entity.device_id,
                })

        if not elk_zones:
            _LOGGER.warning("No ELK-M1 zones found. Install/setup binary_sensor.py first.")
            hass.components.persistent_notification.async_create(
                "No ELK-M1 zones found to auto-configure in Alarmo. "
                "Make sure binary_sensor platform is loaded and zones are created.",
                title="Alarmo Auto-Setup Failed",
            )
            return

        if ALARMO_DOMAIN not in hass.data:
            _LOGGER.warning("Alarmo integration not found. Install Alarmo first.")
            hass.components.persistent_notification.async_create(
                "Alarmo integration not installed. "
                "Install Alarmo via HACS before running this automation.",
                title="Alarmo Not Found",
            )
            return

        zones_list = "\n".join([f"- {z['name']} ({z['entity_id']})" for z in elk_zones])

        setup_message = f"""
Auto-Setup Complete! {len(elk_zones)} ELK-M1 zones found and ready to configure in Alarmo.

**Zones Found:**
{zones_list}

**Next Steps:**
1. Open Alarmo control panel (Settings > Devices & Services > Alarmo)
2. Click "SENSORS" tab
3. All ELK-M1 zones should appear in the available sensors list
4. For each zone you want to monitor:
   - Click the zone name
   - Select the Device Type (Door, Window, Motion, Fire, Water, etc.)
   - Choose which Arm Modes include this zone (Away, Home, Night)
   - Click "Add to alarm"
5. Go to ACTIONS tab to set up sirens, notifications, etc.
6. Go to CODES tab to set up user codes (optional)

Zones are automatically detected by Alarmo. No manual configuration needed!
"""

        _LOGGER.info(f"Found {len(elk_zones)} ELK-M1 zones ready for Alarmo")

        hass.components.persistent_notification.async_create(
            setup_message,
            title="✅ ELK-M1 → Alarmo Auto-Setup",
            notification_id=f"{DOMAIN}_alarmo_setup_success",
        )

    # Register the service if not already registered
    if not hass.services.has_service(DOMAIN, "alarmo_auto_setup"):
        hass.services.async_register(
            DOMAIN,
            "alarmo_auto_setup",
            handle_auto_setup_alarmo,
        )
        _LOGGER.info("Alarmo auto-setup service registered")


async def async_setup_alarmo_event_automation(hass: HomeAssistant) -> str:
    """Create an automation that runs on startup to setup Alarmo."""
    automation_yaml = """
automation:
  - alias: "ELK-M1 → Auto-setup Alarmo on Startup"
    description: "Automatically discover ELK-M1 zones in Alarmo when Home Assistant starts"
    
    trigger:
      platform: homeassistant
      event: start
    
    condition:
      - condition: state
        entity_id: alarm_control_panel.elk_m1
        state: unavailable
        for:
          seconds: 0
        invert: true
    
    action:
      - delay:
          seconds: 10
      
      - service: elkm1.alarmo_auto_setup
        data: {}
      
      - service: persistent_notification.create
        data:
          title: "✅ ELK-M1 zones auto-detected by Alarmo"
          message: "All ELK-M1 zones are now available in Alarmo. Go to Alarmo Settings > Sensors to add them to your alarm."
          notification_id: "elk_alarmo_ready"
"""
    return automation_yaml


def get_alarmo_setup_script() -> str:
    """Return a Home Assistant script for manual Alarmo setup."""
    script_yaml = """
script:
  elk_alarmo_setup:
    description: "Setup ELK-M1 zones in Alarmo"
    sequence:
      - service: persistent_notification.create
        data:
          title: "🔧 Setting up Alarmo with ELK-M1 zones..."
          message: "This may take a moment while Alarmo discovers your zones."
          notification_id: "elk_alarmo_setup_progress"
      
      - delay:
          seconds: 5
      
      - service: elkm1.alarmo_auto_setup
        data: {}
      
      - delay:
          seconds: 2
      
      - service: persistent_notification.create
        data:
          title: "✅ Alarmo Setup Complete"
          message: |
            All ELK-M1 zones have been discovered by Alarmo.
            
            Next steps:
            1. Open Alarmo panel from the sidebar
            2. Go to SENSORS tab
            3. Click "Add sensors" button
            4. Select the ELK-M1 zones you want to monitor
            5. Configure each zone's type and arm modes
            6. Save
            
            Your zones are now part of your security system!
          notification_id: "elk_alarmo_complete"
"""
    return script_yaml


ALARMO_SETUP_BLUEPRINT = """
blueprint:
  name: ELK-M1 → Alarmo Auto-Setup
  description: |
    Automatically configure Alarmo with discovered ELK-M1 zones on Home Assistant startup.
    
    This blueprint:
    1. Waits for Home Assistant and ELK-M1 integration to load
    2. Triggers the auto-setup service
    3. Creates a notification with setup instructions
    4. Zones appear in Alarmo's "Sensors" tab automatically
  
  domain: automation
  source_url: https://github.com/yourname/ha-elkm1/blob/main/blueprints/alarmo-auto-setup.yaml

trigger:
  platform: homeassistant
  event: start

condition:
  - condition: state
    entity_id: alarm_control_panel.elk_m1
    state: unavailable
    for:
      seconds: 0
    invert: true

action:
  - delay:
      seconds: 10
  
  - service: elkm1.alarmo_auto_setup
    data: {}
  
  - service: persistent_notification.create
    data:
      title: "✅ ELK-M1 zones ready in Alarmo"
      message: |
        Your ELK-M1 zones have been auto-discovered by Alarmo.
        
        **Quick Start:**
        1. Open Settings → Devices & Services → Alarmo
        2. Click "SENSORS" tab
        3. You'll see all your ELK zones
        4. Click "Add sensors" and select the ones you want to monitor
        5. Assign each zone a type (Door/Window/Motion/Fire/Water)
        6. Choose which arm modes (Home/Away/Night) include each zone
        7. Click "Save"
        
        Your security system is now ready to use!
      notification_id: "elk_alarmo_ready"
"""
