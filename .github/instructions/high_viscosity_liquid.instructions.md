---
description: >
  Use when working with high_viscosity_liquid materials: registering materials in the
  Resource Manager, reading dispensing parameters in node actions, writing calibration
  results, or editing material-related notebook cells.
applyTo: "**"
---

# High Viscosity Liquid — Project Rules

## Material

### Registration in Resource Manager

| Field | Value |
|---|---|
| `resource_name` | Unique name for the material. Must exactly match the `material_name` argument in node actions. |
| `resource_class` | Always `"high_viscosity_liquid"` |

---

### attributes Schema (v1.3)

```yaml
schema_version: "1.2"

product_info:
  material_name    (str, required) : raw material name
  common_name      (str)           : common / trade name
  manufacturer     (str)           : supplier name
  cas_number       (str)           : CAS registry number
  lot_number       (str)           : lot / batch number
  price_jpy_per_kg (float)         : unit price [JPY/kg]
  application      (str)           : e.g. "plasticizer", "pigment", "hardener", "base resin"
  chemical_class   (str)           : e.g. "amine", "silicone", "hydrocarbon"

physical_properties_nominal:        # Manufacturer's catalog / nominal values only
  density_g_per_cm3 (float)
  viscosity_mPas    (float)

dispensing_params:
  "{device_name}":                  # Key = section name in devices/devices.settings.yaml
    suck_back:                      # Device-level suck-back params (pressure-independent)
      delay_s   (float)             : wait time after dispense before suck-back [s]
      volume_ml (float)             : suck-back volume [mL]
    "{pressure_MPa}":               # Key = f"{pressure_mpa}MPa", e.g. "0.1MPa"
      throughput:                   # Throughput: maximum stable speed
        speed_ml_per_min  (float)   : maximum stable dispensing speed [mL/min]
        density_g_per_cm3 (float)   : density measured at this speed [g/cm³]
      accuracy:                     # Accuracy: lowest speed (closest to true value)
        speed_ml_per_min  (float)   : lowest speed used in calibration [mL/min]
        density_g_per_cm3 (float)   : density measured at this speed [g/cm³]
      min_shot:                     # Minimum shot — measured manually
        commanded_volume_ml (float) : commanded dispense volume [mL]
        wait_s              (float) : wait time after dispense [s]
        measured_mass_mg    (float) : measured dispensed mass [mg]
      calibrated_at               (str)      : ISO datetime, e.g. "2026-05-12T10:00:00"
      source_type                 (str)      : "manual" | "workflow"
      source_datapoint_id         (str|null) : datapoint_id in Data Manager; null when source_type == "manual"
```

---

### `dispensing_params` Key Naming Rules

- **Outer key (device name)** — use the section name from `devices/devices.settings.yaml` as-is (e.g. `"high_viscosity_dispenser"`)
- **`suck_back`** — fixed key for device-level suck-back parameters (pressure-independent)
- **Pressure key** — generated as `f"{pressure_mpa}MPa"` (e.g. `"0.1MPa"`). Lives at the same level as `suck_back`.
- For multiple dispensers, add one entry per device.

---

### Reading Pattern from Node Actions

```python
material = self.resource_client.query_resource(resource_name=material_name)
attrs = material.attributes or {}

device_params = attrs.get("dispensing_params", {}).get("high_viscosity_dispenser", {})

# Read suck_back (used in calibrate_dispenser and weigh_and_dispense)
suck_back = device_params.get("suck_back", {})
suck_back_volume_ml = suck_back.get("volume_ml")
suck_back_delay_s   = suck_back.get("delay_s")

# Read dispensing_params (used in weigh_and_dispense)
pressure_params = device_params.get("0.1MPa", {})
# Throughput
throughput_speed   = pressure_params.get("throughput", {}).get("speed_ml_per_min")
throughput_density = pressure_params.get("throughput", {}).get("density_g_per_cm3")
# Accuracy
accuracy_speed   = pressure_params.get("accuracy", {}).get("speed_ml_per_min")
accuracy_density = pressure_params.get("accuracy", {}).get("density_g_per_cm3")
```

---

### Schema Version History

| version | date | changes |
|---|---|---|
| 0.0 | initial | — |
| 1.0 | 2026-05-12 | `dispensing_params`: removed `g_per_rev`, renamed `max_stable_speed_rps` → `max_stable_speed_ml_per_min`, split `source_datapoint_id` → `source_type` + `source_datapoint_id`; added `suck_back_params` |
| 1.1 | 2026-05-12 | `dispensing_params`: added `device_name` as outer key to support multiple dispensers per material |
| 1.2 | 2026-05-13 | `physical_properties` → `physical_properties_nominal` (nominal only; measured values removed); `suck_back_params` (top-level) → `dispensing_params[device][suck_back]` (device-level); `dispensing_params[device][pressure]`: `max_stable_speed_ml_per_min` → `throughput` / `accuracy` subsections (each with speed + density) |
| 1.3 | 2026-05-14 | `dispensing_params[device][pressure]`: added `min_shot` subsection (commanded_volume_ml, wait_s, measured_mass_mg) |

Migration functions are defined in `notebooks/material_management.ipynb` (schema setup cell).
