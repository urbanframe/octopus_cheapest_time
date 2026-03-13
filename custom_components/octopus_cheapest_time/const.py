"""Constants for the Octopus Cheapest Time integration."""

DOMAIN = "octopus_cheapest_time"

# Hub (integration-level) config — entered once
CONF_CURRENT_RATE_ENTITY = "current_rate_entity"
CONF_NEXT_RATE_ENTITY = "next_rate_entity"

# Per-task config
CONF_TASK_NAME = "task_name"
CONF_TASK_DURATION = "task_duration"
CONF_THRESHOLD_PENCE = "threshold_pence"

# Always search the full 48-hour window (today + tomorrow rates)
SEARCH_WINDOW_HOURS = 48

DEFAULT_SCAN_INTERVAL = 300  # 5 minutes

# Octopus Energy rate slot attribute keys
OCTOPUS_ATTR_RATES = "rates"
OCTOPUS_ATTR_START = "start"
OCTOPUS_ATTR_END = "end"
OCTOPUS_ATTR_VALUE = "value_inc_vat"

# Sensor output attribute names
ATTR_CHEAPEST_START = "cheapest_start"
ATTR_CHEAPEST_END = "cheapest_end"
ATTR_AVERAGE_COST_GBP = "average_cost_per_kwh"
ATTR_AVERAGE_COST_PENCE = "average_cost_pence_per_kwh"
ATTR_TIME_UNTIL_START = "time_until_start_hours"
ATTR_TASK_DURATION_MINUTES = "task_duration_minutes"
ATTR_TODAY_SLOTS = "today_rate_slots"
ATTR_TOMORROW_SLOTS = "tomorrow_rate_slots"
ATTR_TOTAL_WINDOWS = "total_windows_checked"
ATTR_ALL_WINDOWS = "cheapest_windows"
ATTR_CURRENT_RATE_ENTITY = "current_rate_entity"
ATTR_NEXT_RATE_ENTITY = "next_rate_entity"
ATTR_THRESHOLD_PENCE = "threshold_pence"
