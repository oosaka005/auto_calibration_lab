---
description: >
  Use when working with high_viscosity_liquid materials: registering materials in the
  Resource Manager, reading dispensing parameters in node actions, writing calibration
  results, or editing material-related notebook cells.
applyTo: "**"
---

# High Viscosity Liquid — Project Rules

## 材料 (Material)

### Resource Manager への登録

| フィールド | 値 |
|---|---|
| `resource_name` | 材料の一意な名前。Node action の引数 `material_name` と完全一致すること |
| `resource_class` | `"high_viscosity_liquid"` 固定 |

---

### attributes スキーマ（v1.2）

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
      throughput:                   # スループット重視（最高安定速度）
        speed_ml_per_min  (float)   : maximum stable dispensing speed [mL/min]
        density_g_per_cm3 (float)   : density measured at this speed [g/cm³]
      accuracy:                     # 精度重視（最低速度 = 真値に最も近い）
        speed_ml_per_min  (float)   : lowest speed used in calibration [mL/min]
        density_g_per_cm3 (float)   : density measured at this speed [g/cm³]
      calibrated_at               (str)      : ISO datetime, e.g. "2026-05-12T10:00:00"
      source_type                 (str)      : "manual" | "workflow"
      source_datapoint_id         (str|null) : datapoint_id in Data Manager; null when source_type == "manual"
```

---

### `dispensing_params` キー命名規則

- **外側のキー（デバイス名）** — `devices/devices.settings.yaml` のセクション名をそのまま使う（例：`"high_viscosity_dispenser"`）
- **`suck_back`** — 固定キー。圧力に依存しないデバイスレベルのサックバックパラメータ
- **圧力キー** — `f"{pressure_mpa}MPa"` で生成する（例：`"0.1MPa"`）。`suck_back` と同じ階層に混在
- 複数のディスペンサーを使う場合は、デバイスごとにエントリを追加する

---

### Node action からの読み取りパターン

```python
material = self.resource_client.query_resource(resource_name=material_name)
attrs = material.attributes or {}

device_params = attrs.get("dispensing_params", {}).get("high_viscosity_dispenser", {})

# suck_back を読む（calibrate_dispenser, weigh_and_dispense で使用）
suck_back = device_params.get("suck_back", {})
suck_back_volume_ml = suck_back.get("volume_ml")
suck_back_delay_s   = suck_back.get("delay_s")

# dispensing_params を読む（weigh_and_dispense で使用）
pressure_params = device_params.get("0.1MPa", {})
# スループット重視
throughput_speed   = pressure_params.get("throughput", {}).get("speed_ml_per_min")
throughput_density = pressure_params.get("throughput", {}).get("density_g_per_cm3")
# 精度重視
accuracy_speed   = pressure_params.get("accuracy", {}).get("speed_ml_per_min")
accuracy_density = pressure_params.get("accuracy", {}).get("density_g_per_cm3")
```

---

### スキーマバージョン履歴

| version | date | changes |
|---|---|---|
| 0.0 | initial | — |
| 1.0 | 2026-05-12 | `dispensing_params`: removed `g_per_rev`, renamed `max_stable_speed_rps` → `max_stable_speed_ml_per_min`, split `source_datapoint_id` → `source_type` + `source_datapoint_id`; added `suck_back_params` |
| 1.1 | 2026-05-12 | `dispensing_params`: added `device_name` as outer key to support multiple dispensers per material |
| 1.2 | 2026-05-13 | `physical_properties` → `physical_properties_nominal`（nominal のみ、measured 廃止）; `suck_back_params`（トップレベル）→ `dispensing_params[device][suck_back]`（デバイスレベル）; `dispensing_params[device][pressure]`: `max_stable_speed_ml_per_min` → `throughput` / `accuracy` サブセクション（各自 speed + density） |

Migration functions are defined in `notebooks/material_management.ipynb` (schema setup cell).
