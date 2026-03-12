"""Config flow for Octopus Cheapest Time.

Architecture
============
One config entry per TASK. Each entry holds all four values:
  - current_rate_entity
  - next_rate_entity
  - task_name
  - task_duration

Setup flow (2 steps):
  Step 1 (user)        — enter the two rate entities (shown once; subsequent
                         "Add Integration" runs skip straight to add_task).
  Step 2 (first_task)  — enter the first task name + duration.

Adding more tasks:
  Run "Add Integration" again → skips to add_task, reusing saved entities.

Options flow (menu with two choices):
  "Edit task"           — change name / duration for this entry only.
  "Update rate entities" — change the two entity IDs; change is propagated
                           to ALL existing task entries automatically.

IMPORTANT: entity fields in the options flow always use cv.string (plain text),
never vol.In(), to avoid the 500 Internal Server Error caused by schema
conflicts when HA loads the options form.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_CURRENT_RATE_ENTITY,
    CONF_NEXT_RATE_ENTITY,
    CONF_TASK_NAME,
    CONF_TASK_DURATION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _octopus_entities(hass: HomeAssistant) -> list[str]:
    """Sorted list of likely OctopusEnergy rate event entities."""
    reg = er.async_get(hass)
    found = [
        e.entity_id for e in reg.entities.values()
        if e.platform == "octopus_energy"
        or ("octopus_energy" in e.entity_id and "day_rates" in e.entity_id)
    ]
    return sorted(found)


def _entity_validator(hass: HomeAssistant) -> vol.Validator:
    """Dropdown if OctopusEnergy entities are found, otherwise free text."""
    entities = _octopus_entities(hass)
    return vol.In(entities) if entities else cv.string


def _existing_entry(hass: HomeAssistant) -> config_entries.ConfigEntry | None:
    """Return the first existing entry for this domain."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _task_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_TASK_NAME, default=d.get(CONF_TASK_NAME, "")): cv.string,
        vol.Required(CONF_TASK_DURATION, default=d.get(CONF_TASK_DURATION, 60)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
    })


def _rate_entity_schema(defaults: dict | None = None) -> vol.Schema:
    """
    Schema for the rate entity fields.
    Always uses cv.string — never vol.In() — so it is safe to use in the
    options flow without risking a 500 error.
    """
    d = defaults or {}
    return vol.Schema({
        vol.Required(
            CONF_CURRENT_RATE_ENTITY,
            default=d.get(CONF_CURRENT_RATE_ENTITY, ""),
        ): cv.string,
        vol.Required(
            CONF_NEXT_RATE_ENTITY,
            default=d.get(CONF_NEXT_RATE_ENTITY, ""),
        ): cv.string,
    })


# ---------------------------------------------------------------------------
# Main config flow
# ---------------------------------------------------------------------------

class OctopusCheapestTimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two-step setup; subsequent runs go straight to add_task."""

    VERSION = 1

    def __init__(self) -> None:
        self._current_entity: str = ""
        self._next_entity: str = ""

    async def async_step_user(self, user_input: dict | None = None):
        """First run → entity setup. Subsequent runs → add_task directly."""
        existing = _existing_entry(self.hass)
        if existing is not None:
            saved = {**existing.data, **existing.options}
            self._current_entity = saved.get(CONF_CURRENT_RATE_ENTITY, "")
            self._next_entity = saved.get(CONF_NEXT_RATE_ENTITY, "")
            return await self.async_step_add_task()

        errors: dict = {}
        if user_input is not None:
            self._current_entity = user_input[CONF_CURRENT_RATE_ENTITY].strip()
            self._next_entity = user_input[CONF_NEXT_RATE_ENTITY].strip()
            if not self._current_entity:
                errors[CONF_CURRENT_RATE_ENTITY] = "entity_required"
            elif not self._next_entity:
                errors[CONF_NEXT_RATE_ENTITY] = "entity_required"
            else:
                return await self.async_step_first_task()

        sel = _entity_validator(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CURRENT_RATE_ENTITY, default=""): sel,
                vol.Required(CONF_NEXT_RATE_ENTITY, default=""): sel,
            }),
            errors=errors,
        )

    async def async_step_first_task(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            name = user_input[CONF_TASK_NAME].strip()
            duration = user_input[CONF_TASK_DURATION]
            if not name:
                errors[CONF_TASK_NAME] = "name_required"
            elif duration < 1:
                errors[CONF_TASK_DURATION] = "invalid_duration"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_CURRENT_RATE_ENTITY: self._current_entity,
                        CONF_NEXT_RATE_ENTITY: self._next_entity,
                        CONF_TASK_NAME: name,
                        CONF_TASK_DURATION: duration,
                    },
                )
        return self.async_show_form(
            step_id="first_task",
            data_schema=_task_schema(),
            errors=errors,
        )

    async def async_step_add_task(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            name = user_input[CONF_TASK_NAME].strip()
            duration = user_input[CONF_TASK_DURATION]
            if not name:
                errors[CONF_TASK_NAME] = "name_required"
            elif duration < 1:
                errors[CONF_TASK_DURATION] = "invalid_duration"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_CURRENT_RATE_ENTITY: self._current_entity,
                        CONF_NEXT_RATE_ENTITY: self._next_entity,
                        CONF_TASK_NAME: name,
                        CONF_TASK_DURATION: duration,
                    },
                )
        return self.async_show_form(
            step_id="add_task",
            data_schema=_task_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OctopusCheapestTimeOptionsFlow()


# ---------------------------------------------------------------------------
# Options flow — menu → edit task OR update rate entities
# ---------------------------------------------------------------------------

class OctopusCheapestTimeOptionsFlow(config_entries.OptionsFlow):
    """
    Two-option menu:
      1. Edit task  — name + duration for this entry only.
      2. Update rate entities — entity IDs propagated to all task entries.
    """

    async def async_step_init(self, user_input: dict | None = None):
        """Show a menu: edit task or update rate entities."""
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "edit_task": "Edit task name / duration",
                "rate_entities": "Update rate entities",
            },
        )

    # ------------------------------------------------------------------
    # Menu option 1: edit task name + duration
    # ------------------------------------------------------------------
    async def async_step_edit_task(self, user_input: dict | None = None):
        errors: dict = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            name = user_input.get(CONF_TASK_NAME, "").strip()
            duration = user_input[CONF_TASK_DURATION]
            if not name:
                errors[CONF_TASK_NAME] = "name_required"
            elif duration < 1:
                errors[CONF_TASK_DURATION] = "invalid_duration"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="edit_task",
            data_schema=_task_schema(current),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Menu option 2: update rate entities across all task entries
    # ------------------------------------------------------------------
    async def async_step_rate_entities(self, user_input: dict | None = None):
        errors: dict = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            current_entity = user_input[CONF_CURRENT_RATE_ENTITY].strip()
            next_entity = user_input[CONF_NEXT_RATE_ENTITY].strip()

            if not current_entity:
                errors[CONF_CURRENT_RATE_ENTITY] = "entity_required"
            elif not next_entity:
                errors[CONF_NEXT_RATE_ENTITY] = "entity_required"
            else:
                # Propagate the new entity IDs to every task entry in the domain
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    new_data = {
                        **entry.data,
                        CONF_CURRENT_RATE_ENTITY: current_entity,
                        CONF_NEXT_RATE_ENTITY: next_entity,
                    }
                    self.hass.config_entries.async_update_entry(entry, data=new_data)

                # Return empty options — the real change is in entry.data above
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="rate_entities",
            data_schema=_rate_entity_schema(current),
            errors=errors,
            description_placeholders={
                "current": current.get(CONF_CURRENT_RATE_ENTITY, ""),
                "next": current.get(CONF_NEXT_RATE_ENTITY, ""),
            },
        )
