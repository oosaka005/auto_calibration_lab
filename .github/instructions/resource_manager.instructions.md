---
description: >
  Use when working with the MADSci Resource Manager: registering, querying, updating, or
  removing resources. Covers all resource types, required/optional fields, use cases,
  and data storage location.
applyTo: "**"
---

# Resource Manager

Tracks physical items in the lab (reagents, containers, racks, etc.) and makes them available to node actions.

- **Port:** `8003`
- **Swagger UI:** http://localhost:8003/docs
- **Start command:** `docker compose up -d madsci_postgres event_manager resource_manager`

---

## Common Fields (all types inherit these)

| Field | Type | Required | Description |
|---|---|---|---|
| `resource_name` | `str` | **Required** | Unique name. Used as key from actions |
| `resource_class` | `str` | Recommended | Label for filtering (e.g. `"high_viscosity_liquid"`) |
| `resource_id` | `str` (ULID) | Auto-generated | Assigned by the system |
| `resource_description` | `str` | Optional | Free-text description |
| `attributes` | `dict` | Optional (recommended) | Free-form dict for custom data |
| `base_type` | `str` | Auto-set | Set automatically per type |
| `parent_id` | `str` | Optional | Parent resource ID if nested |
| `created_at` / `updated_at` | `datetime` | Auto-set | Set by the server |
| `removed` | `bool` | Auto-set | Soft-delete flag; set by `remove_resource()` |

---

## Resource Types

### `Resource` — base class
Generic resource. Rarely used directly.

---

### `Consumable` — consumed items
`from madsci.common.types.resource_types import Consumable`

Reagents, liquids, powders, etc.

| Field | Type | Default | Description |
|---|---|---|---|
| `quantity` | `float >= 0` | `0` | Current amount |
| `capacity` | `float >= 0` | `None` | Max capacity (None = unlimited) |
| `unit` | `str` | `None` | Unit (e.g. `"g"`, `"mL"`) |

Validation: `quantity <= capacity` when capacity is set.

---

### `DiscreteConsumable` — integer-counted items
Same as `Consumable` but `quantity`/`capacity` are `int`.
Use for: pipette tips, tubes.

---

### `ContinuousConsumable` — float-quantity items
Same as `Consumable` but `quantity`/`capacity` are explicitly `float`.
Use when you want to be explicit about continuous measurement.

---

### `Asset` — non-consumed items
Samples, labware, fixtures. No additional fields beyond `Resource`.

---

### `Container` — holds other resources

| Field | Type | Description |
|---|---|---|
| `capacity` | `int` | Max number of children |
| `children` | `dict[str, Resource]` | Stored resources (key → resource) |

---

### `Collection`
Subclass of `Container`. Supports random access via dict keys.

---

### `Stack` — LIFO
Last-in, first-out. Index 0 = bottom. Use for vertical magazines.

---

### `Queue` — FIFO
First-in, first-out. Index 0 = front. Use for conveyor belts.

---

### `Row` — 1D array
Required field: `columns: int`. Use for single-row tube racks.

---

### `Grid` — 2D array
Required fields: `rows: int`, `columns: int`. Use for 96-well plates.

---

### `VoxelGrid` — 3D array
Required fields: `rows`, `columns`, `layers`. Use for 3D racks.

---

### `Slot` — single-item holder
Capacity is always `1`.

---

### `Pool` — mixed consumables
`children: dict[str, Consumable]`. Multiple liquids can coexist.
Use for microplate wells, reservoirs.

---

## Data Storage

Resource Manager uses **PostgreSQL**.

```
{project root}/.madsci/postgresql/data/
```

Docker container: `madsci_postgres` (port `5432`).
The `data/` directory contains PostgreSQL binary files — do not edit directly.

---

## Inspecting and Managing Data

- **Notebook:** use `notebooks/material_management.ipynb` (List / Add / Update / Remove cells)
- **Swagger UI:** http://localhost:8003/docs → `POST /resource/query` → "Try it out"

---

## Soft Delete

`resource_client.remove_resource()` sets `removed = True` — it does **not** physically delete the record.
Soft-deleted resources are excluded from normal `query_resource()` results but remain in PostgreSQL.
