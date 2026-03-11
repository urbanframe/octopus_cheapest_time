# Octopus Energy – Cheapest Time Scheduler

A Home Assistant custom integration that reads upcoming electricity rates from the [BottlecapDave HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) integration and calculates the cheapest time window to run a task.

---

## Features

- Add **multiple tasks** (e.g. Dishwasher, EV Charge, Washing Machine) — each gets its own sensor
- Merges **today's and tomorrow's** Agile rates into a single 48-hour window automatically
- Each sensor state is the **cheapest start time** as a timestamp (displays in your local timezone)
- Sensor attributes include cost in both **£/kWh and pence/kWh**
- `time_until_start_hours` is always **rounded to the nearest 0.5 hours**
- A dedicated **numeric sensor** (`sensor.time_until_start_<task>`) exposes hours until start — readable directly by ESPHome and other integrations
- Updates every **5 minutes**
- Edit task name or duration at any time via **Configure** — no re-setup needed

---

## Prerequisites

1. Home Assistant 2024.1 or later
2. [BottlecapDave HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) installed and configured
3. An Octopus Agile tariff (other tariffs that provide half-hourly rate schedules will also work)

---

## Installation

### Manual

1. Copy the `custom_components/octopus_cheapest_time/` folder into your HA `config/custom_components/` directory
2. Delete any existing `__pycache__` folder inside it if updating from a previous version
3. Restart Home Assistant

### Via HACS

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add your repository URL with category **Integration**
3. Search for "Octopus Cheapest Time" and install, then restart Home Assistant

---

## Setup

### Step 1 — Add the integration (once)

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Octopus Energy - Cheapest Time Scheduler"**
3. Enter your two OctopusEnergy rate event entities:

| Field | Description | Example |
|-------|-------------|---------|
| **Today's rates entity** | The `current_day_rates` event entity | `event.octopus_energy_electricity_20e5081399_2500000908478_current_day_rates` |
| **Tomorrow's rates entity** | The `next_day_rates` event entity | `event.octopus_energy_electricity_20e5081399_2500000908478_next_day_rates` |

These are entered **once** and shared across all tasks. If OctopusEnergy entities appear in a dropdown, you can select them directly.

### Step 2 — Add your first task

Immediately after entering the rate entities you are prompted for:

| Field | Description | Example |
|-------|-------------|---------|
| **Task name** | A friendly label | `Dishwasher` |
| **Duration (minutes)** | How long the task runs | `90` |

A sensor named `sensor.cheapest_start_dishwasher` is created straight away.

### Adding more tasks

Go to **Settings → Devices & Services → Add Integration** again and search for the same integration. Because the rate entities are already configured you will be taken straight to the task name/duration form. Each new task creates an additional sensor.

---

## Finding your rate entity IDs

In Developer Tools → States, look for event entities matching this pattern:

```
event.octopus_energy_electricity_<serial>_<mpan>_current_day_rates
event.octopus_energy_electricity_<serial>_<mpan>_next_day_rates
```

You can confirm they are correct by checking that their attributes include a `rates` list containing half-hourly slots with `start`, `end`, and `value_inc_vat` keys.

> **Note:** `current_day_rates` always covers from now until midnight. `next_day_rates` covers midnight through the following midnight and is published at around **4pm each day**. Before 4pm, `next_day_rates` may be empty — the integration will still find the cheapest window using the remaining slots from today.

---

## Sensor reference

Each task creates **two sensors**:

| Sensor | Entity ID pattern | Description |
|--------|-------------------|-------------|
| Cheapest Start | `sensor.cheapest_start_<task>` | Timestamp of the cheapest window start |
| Time Until Start | `sensor.time_until_start_<task>` | Hours until that start, rounded to 0.5 |

### Cheapest Start sensor

#### State

An **ISO 8601 timestamp** of the cheapest available start time. Home Assistant displays this in your local timezone. The value is `unknown` if no suitable window is found (e.g. before tomorrow's rates are published and today's rates are all in the past).

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `cheapest_start` | ISO timestamp | Start of the cheapest window |
| `cheapest_end` | ISO timestamp | End of the cheapest window (start + duration) |
| `average_cost_per_kwh` | float | Average rate across the window in **£/kWh** inc VAT |
| `average_cost_pence_per_kwh` | float | Same value in **pence/kWh** inc VAT |
| `time_until_start_hours` | float | Hours until the cheapest start, **rounded to nearest 0.5** |
| `task_duration_minutes` | int | The configured task duration |
| `current_rate_entity` | string | The today's rates entity being used |
| `next_rate_entity` | string | The tomorrow's rates entity being used |
| `today_rate_slots` | int | Number of half-hourly slots loaded from today's entity |
| `tomorrow_rate_slots` | int | Number of half-hourly slots loaded from tomorrow's entity |
| `total_windows_checked` | int | Total number of candidate windows evaluated |
| `cheapest_windows` | list | Top 5 cheapest windows (start, end, pence/kWh each) |

### Example attributes

```yaml
cheapest_start: "2026-03-11T02:00:00+00:00"
cheapest_end:   "2026-03-11T03:30:00+00:00"
average_cost_per_kwh: 0.07378
average_cost_pence_per_kwh: 7.378
time_until_start_hours: 3.5
task_duration_minutes: 90
current_rate_entity: "event.octopus_energy_electricity_20e5081399_2500000908478_current_day_rates"
next_rate_entity: "event.octopus_energy_electricity_20e5081399_2500000908478_next_day_rates"
today_rate_slots: 46
tomorrow_rate_slots: 48
total_windows_checked: 61
cheapest_windows:
  - start: "2026-03-11T02:00:00+00:00"
    end:   "2026-03-11T03:30:00+00:00"
    average_cost_pence_per_kwh: 7.378
  - start: "2026-03-11T02:30:00+00:00"
    end:   "2026-03-11T04:00:00+00:00"
    average_cost_pence_per_kwh: 8.484
  - start: "2026-03-11T01:30:00+00:00"
    end:   "2026-03-11T03:00:00+00:00"
    average_cost_pence_per_kwh: 9.12
```

### Time Until Start sensor

#### State

A **float** representing hours until the cheapest start time, rounded to the nearest 0.5. Returns `unknown` if no window is found.

| Value | Meaning |
|-------|---------|
| `0.0` | Start now (window is current or just passed) |
| `0.5` | Start in 30 minutes |
| `3.5` | Start in 3.5 hours |

This sensor is suitable for direct use in **ESPHome** via the `homeassistant` sensor platform, dashboard conditions, and notification messages without needing a template sensor.

---

## Automation examples

### Trigger a switch at the cheapest time

```yaml
alias: "Start Dishwasher at Cheapest Time"
trigger:
  - platform: time
    at: "sensor.cheapest_start_dishwasher"
action:
  - service: switch.turn_on
    target:
      entity_id: switch.dishwasher_plug
```

### Send a notification when the cheapest time is found

```yaml
alias: "Notify cheapest dishwasher window"
trigger:
  - platform: state
    entity_id: sensor.cheapest_start_dishwasher
action:
  - service: notify.mobile_app_my_phone
    data:
      message: >
        Best time to run the dishwasher:
        {{ state_attr('sensor.cheapest_start_dishwasher', 'cheapest_start') }}
        in {{ state_attr('sensor.cheapest_start_dishwasher', 'time_until_start_hours') }} hours
        at {{ state_attr('sensor.cheapest_start_dishwasher', 'average_cost_pence_per_kwh') }}p/kWh avg
```

---

## How the algorithm works

1. Rates are read from both event entities: `current_day_rates` (now until midnight) and `next_day_rates` (midnight to midnight, published ~4pm daily)
2. The two sets are merged and deduplicated by slot start time
3. All future slots within the 48-hour window are sorted chronologically
4. A **sliding window** moves slot-by-slot: for each possible start, contiguous 30-minute slots are accumulated until the full task duration is covered
5. The average £/kWh is calculated for each candidate window
6. All windows are sorted cheapest-first; the best is returned as the sensor state
7. `time_until_start_hours` is rounded to the nearest 0.5 so it's clean to use in notifications and conditions

---

## ESPHome example

The `sensor.time_until_start_<task>` sensor can be read directly in ESPHome — no template sensor needed in HA.

```yaml
sensor:
  - platform: homeassistant
    id: wash_40deg_start
    entity_id: sensor.time_until_start_40degwash
    on_value:
      then:
        - if:
            condition:
              lambda: return (isnan(id(wash_40deg_start).state));
            then:
              - lvgl.label.update:
                  id: InfoDisplaywash_40deg_start
                  text: "TBC"
            else:
              - lvgl.label.update:
                  id: InfoDisplaywash_40deg_start
                  text:
                    format: "%.1f Hrs"
                    args: [ 'x' ]
```

The `isnan` check handles the `unknown` state (no rates available yet). The value is already rounded to 0.5 so `"%.1f"` will always display cleanly as `0.0`, `0.5`, `1.0`, `1.5` etc.

---

## Editing a task

Click **Configure** on any task entry in **Settings → Devices & Services** to update the task name or duration. The sensor reloads automatically with the new values.

> The rate entities (today/tomorrow) are set once at integration level and are not editable via Configure. To change them, remove the integration and add it again.

---

## Troubleshooting

**Sensor is `unknown` or `unavailable`**
Rates may not be loaded yet — the integration retries every 5 minutes. Check that the OctopusEnergy integration is working and the rate entities have a `rates` attribute with slots in it.

**`today_rate_slots` is 0**
Check the `current_rate_entity` ID is correct and that the OctopusEnergy integration has fetched rates successfully. `current_day_rates` should always have slots.

**`tomorrow_rate_slots` is 0**
This is normal before ~4pm — Agile rates for the next day are published around that time. The sensor will continue working with today's remaining rates and pick up tomorrow's automatically once they appear.

**No windows found**
All of today's remaining slots have passed and tomorrow's rates haven't been published yet. This can occur in the early afternoon before ~4pm. The sensor will recover automatically once tomorrow's rates are published.

**Sensor stopped updating**
Check HA logs for errors under `custom_components.octopus_cheapest_time`. Reloading the integration via Settings → Devices & Services usually resolves transient issues.
