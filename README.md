# Octopus Energy – Cheapest Time Scheduler

A Home Assistant custom integration that reads upcoming electricity rates from the [BottlecapDave HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) integration and calculates the **cheapest time window** to run a task.

---

## Features

- Add **multiple tasks** (e.g. "Dishwasher", "EV Charge", "Washing Machine")
- Each task gets its own **sensor** showing the optimal start time
- Configurable **task duration** (in minutes)
- Configurable **search window** (how many hours ahead to look, 1–48)
- Sensor attributes include:
  - `cheapest_start` – ISO timestamp of best start
  - `cheapest_end` – ISO timestamp of task completion
  - `time_until_start_hours` – hours until start, **rounded to nearest 0.5**
  - `average_cost_per_kwh` – average rate across the window (p/kWh)
  - `task_duration_minutes` – the configured duration
  - `cheapest_windows` – top 5 cheapest windows for reference
  - `total_slots_checked` – how many windows were evaluated
- Updates every **5 minutes** automatically
- Edit settings at any time via the **Options** flow (no re-setup needed)

---

## Prerequisites

1. Home Assistant (2023.x or later)
2. [BottlecapDave HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) installed and configured
3. Your Octopus Energy tariff must provide upcoming rates (Agile tariff works best; Go and Flexible tariffs also work)

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add your repository URL, category: **Integration**
3. Search for "Octopus Cheapest Time" and install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/octopus_cheapest_time/` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Octopus Energy - Cheapest Time Scheduler"**
3. Fill in the form:

| Field | Description | Example |
|-------|-------------|---------|
| **Task Name** | A friendly name for your task | `Dishwasher` |
| **Task Duration (minutes)** | How long the task runs | `90` |
| **Octopus Energy Rate Entity** | The entity with upcoming rates | `sensor.octopus_energy_electricity_<mpan>_<serial>_current_rate` |
| **Search Window (hours)** | How far ahead to look | `24` |

4. Click **Submit** — a new sensor is created immediately.
5. Repeat for as many tasks as you like.

---

## Which rate entity to use?

In the OctopusEnergy integration, look for a sensor with `rates` in its attributes. Common entity IDs look like:

```
sensor.octopus_energy_electricity_1234567890_12A1234567_current_rate
```

You can verify it's the right one by checking **Developer Tools → States**, finding the entity, and confirming it has a `rates` attribute containing a list of upcoming slots.

---

## Sensor Output

### State
The sensor state is an **ISO 8601 timestamp** of the cheapest start time, compatible with HA's `timestamp` device class (displays in your local timezone).

### Attributes example

```yaml
cheapest_start: "2024-01-15T02:00:00+00:00"
cheapest_end:   "2024-01-15T03:30:00+00:00"
average_cost_per_kwh: 8.5
time_until_start_hours: 3.5      # rounded to nearest 0.5
task_duration_minutes: 90
search_window_hours: 24
rate_entity: "sensor.octopus_energy_electricity_..."
total_slots_checked: 42
cheapest_windows:
  - start: "2024-01-15T02:00:00+00:00"
    end:   "2024-01-15T03:30:00+00:00"
    average_cost_per_kwh: 8.5
  - start: "2024-01-15T02:30:00+00:00"
    end:   "2024-01-15T04:00:00+00:00"
    average_cost_per_kwh: 9.1
  ...
```

---

## Automation Example

Turn on a smart plug at the cheapest time:

```yaml
alias: "Start Dishwasher at Cheapest Time"
trigger:
  - platform: template
    value_template: >
      {{ now() >= states('sensor.cheapest_start_dishwasher') | as_datetime }}
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.cheapest_start_dishwasher', 'time_until_start_hours') == 0 }}
action:
  - service: switch.turn_on
    target:
      entity_id: switch.dishwasher_plug
```

Or trigger with a time trigger using the sensor value:

```yaml
alias: "Cheapest Time Notify"
trigger:
  - platform: state
    entity_id: sensor.cheapest_start_dishwasher
action:
  - service: notify.mobile_app_my_phone
    data:
      message: >
        Best time to run dishwasher:
        {{ state_attr('sensor.cheapest_start_dishwasher', 'cheapest_start') }}
        (in {{ state_attr('sensor.cheapest_start_dishwasher', 'time_until_start_hours') }} hours)
        at {{ state_attr('sensor.cheapest_start_dishwasher', 'average_cost_per_kwh') }}p/kWh avg
```

---

## How the algorithm works

1. Reads the `rates` attribute from your chosen OctopusEnergy entity — this is a list of 30-minute price slots
2. Filters to only future slots within the search window
3. Uses a **sliding window** approach: for every possible start slot, it accumulates consecutive 30-min slots until the task duration is covered
4. Calculates the **average cost per kWh** for each window
5. Sorts by cost ascending and returns the cheapest option as the sensor state
6. The `time_until_start_hours` attribute is the difference between now and the cheapest start, **rounded to the nearest 0.5 hours**

---

## Troubleshooting

**Sensor shows "unavailable"**
- Check the rate entity ID is correct
- Verify the OctopusEnergy integration is working and the entity has a `rates` attribute

**No windows found**
- The search window may not have enough future rates yet (Agile rates are published by ~4pm for the next day)
- Try increasing the search window hours

**Sensor stops updating**
- Check HA logs for errors from `custom_components.octopus_cheapest_time`
- Reload the integration via Settings → Devices & Services

---

## Editing a task

Click **Configure** on any task in Settings → Devices & Services to change the duration, rate entity, or search window. The sensor reloads automatically.
