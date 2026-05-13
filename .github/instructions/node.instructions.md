---
description: >
  Use when creating or editing node module files (modules/**/*.py).
  Covers Node class structure, Config class conventions, lifecycle handlers,
  state reporting, action implementation rules, data saving, and error handling.
applyTo: "modules/**"
---

# Node Module Rules

## Overview

Each Node is implemented as a **single Python (`.py`) file** in `modules/{node_name}/`.  

The file always contains exactly **two classes**:

| Class | Role |
|---|---|
| `{NodeName}Config` | Settings loader. Reads `settings.yaml`, `node.settings.yaml`, and `devices.settings.yaml` via walk-up discovery. Instantiates device objects. |
| `{NodeName}` | Node logic. Implements lifecycle handlers and Actions. |

---

## Standard Imports

Every Node file uses the following imports. Add `Path` only when the action generates files.

```python
import logging
import time
from pathlib import Path        # only if the action generates files
from typing import ClassVar, Optional

from madsci.common.types.action_types import ActionFailed, ActionSucceeded
from madsci.common.types.node_types import RestNodeConfig
from madsci.node_module.helpers import action
from madsci.node_module.rest_node_module import RestNode

from devices import DEVICE_REGISTRY
```

---

## node.settings.yaml

Each Node directory must contain a `node.settings.yaml` file with the following fields:

```yaml
node_name: high_viscosity_liquid_weighing   # unique name used by the Workcell and Location Manager
node_type: device                           # always "device" for physical hardware nodes

devices:           # list of device section names from devices/devices.settings.yaml
  - balance        # only listed devices are loaded by this node
  - dispenser

interface_type: fake   # "fake" (simulated) or "real" (hardware). Default: "real"
```

- `node_name` must match the key used in `settings.yaml` under `workcell_nodes:`
- For `devices:` and `interface_type` rules, see `device_settings.instructions.md`

---

## Config Class

- Inherits from `RestNodeConfig`
- Reads device settings from `devices/devices.settings.yaml` and node-specific settings from `node.settings.yaml` via walk-up file discovery
- Device field annotations are auto-generated from `DEVICE_CLASSES` — no manual field definitions needed per device
- To add a device: add one entry to `DEVICE_CLASSES` — nothing else is needed

```python
class MyNodeConfig(
    RestNodeConfig,
    yaml_file=("settings.yaml", "node.settings.yaml", "devices.settings.yaml"),
):
    _extra_search_dirs: ClassVar[tuple[str, ...]] = ("devices",)
    DEVICE_CLASSES: ClassVar[dict] = {...}
```

### Config class is boilerplate

The Config class is **almost identical across all Nodes** in this project.  
The only part that changes per Node is the `# --- Node-specific operation parameters ---` section,  
which holds operation-related parameters that are not tied to a specific device  
(e.g. timeouts, thresholds, iteration counts).

If there are no Node-specific parameters, this section can be left empty.


---

## Node Class

- Inherits from `RestNode`
- Must declare `config` and `config_model` pointing to the Config class
- The device field declaration loop is also **boilerplate** — identical across all Nodes
- The entry point at the bottom of the file is also boilerplate

```python
class MyNode(RestNode):
    config: MyNodeConfig = MyNodeConfig()
    config_model = MyNodeConfig

    # Boilerplate: auto-declare device instance fields from Config
    for _name, _cls in MyNodeConfig.DEVICE_CLASSES.items():
        __annotations__[_name] = Optional[_cls]
        vars()[_name] = None
    del _name, _cls

    # --- Lifecycle handlers (see below) ---
    # --- Actions (see Action Rules) ---


# Entry point — always at the bottom of the file, outside the class
if __name__ == "__main__":
    node = MyNode()
    node.start_node()
```

---

## Lifecycle Handlers

`startup_handler`, `shutdown_handler`, and `state_handler` are **required** for every Node.

### `startup_handler(self) -> None`
Called once when the node starts. Loops over `DEVICE_CLASSES` to instantiate and open all device connections:

```python
def startup_handler(self) -> None:
    for name, cls in self.config.DEVICE_CLASSES.items():
        device = cls(
            **getattr(self.config, name).model_dump(),
            logger=logging.getLogger(name),
        )
        setattr(self, name, device)
```

### `shutdown_handler(self) -> None`
Called when the node stops. Close all device connections:

```python
def shutdown_handler(self) -> None:
    for name in self.config.DEVICE_CLASSES:
        getattr(self, name).close()
```

### `state_handler(self) -> dict[str, Any]`
Called automatically every ~2 seconds (`state_update_interval`). **Always read all device values** — what to display or save is a separate concern.

The return value is **not used** by the framework (`_update_state` discards it). The purpose of this method is to set `self.node_state`. The `-> dict[str, Any]` annotation follows MADSci's example/template convention.

```python
def state_handler(self) -> dict[str, Any]:
    self.node_state = {
        "balance_status": self.balance.status,
        "balance_last_weight_g": self.balance.current_mass_g,
        "dispenser_status": self.dispenser.status,
        "dispenser_motion_status": self.dispenser.motion_status,
    }
```

**`node_state` vs `node_status`**

- `node_state` — physical values polled from devices (weight, position, temperature, etc.). Set in `state_handler`. Used for dashboard display; not stored historically.
- `node_status` — operational state of the node (`busy`, `ready`, `locked`, `paused`, `errored`). Managed automatically. Do not set manually.

---

## Action Rules

### Declaration

- Decorate every action method with `@action`
- Type hints on all arguments are **required** — MADSci uses them to parse and validate incoming arguments automatically
- `blocking=True` is the default — only one blocking action can run at a time per Node
- Use `@action(blocking=False)` for actions that can run concurrently with other actions

Device field names in the Node (e.g. `self.balance`, `self.high_viscosity_dispenser`) come directly from the **section names in `devices/devices.settings.yaml`**. The section name = the field name. This is also the name listed under `devices:` in `node.settings.yaml`.

```python
@action
def dispense_target_mass(self, target_g: float, speed_rps: float) -> dict:
    ...

@action(blocking=False)
def get_status(self) -> dict:
    ...
```

> **Return type annotation rule:**
>
> | 状況 | アノテーション | return |
> |---|---|---|
> | `json_result` に dict を返す（計測結果・評価値など） | `-> dict:` | `ActionSucceeded(json_result={...})` |
> | `json_result` を返さない（動作させるだけ） | `-> ActionResult:` | `ActionSucceeded()` |
>
> **`-> ActionSucceeded:` または `-> ActionResult:` を `json_result` に dict を返すアクションに使ってはいけない。**  
> MADSci の `_extract_json_result_type` がこのアノテーションを FastAPI `response_model` の `json_result` フィールドの型として使うため、  
> dict を入れても `ActionSucceeded` に強制変換されてすべてのフィールドが失われ `json_result: null` になる。

### Return Values and Error Handling

Actions return one of two `ActionResult` subclasses:

| Class | When to use |
|---|---|
| `ActionSucceeded` | Normal completion |
| `ActionFailed` | Any failure (device error, timeout, etc.) |

Other subclasses (`ActionCancelled`, `ActionPaused`, `ActionNotStarted`) exist in the framework but are not returned from action code. 

Wrap the main logic in a `try` block. Device commands raise Python exceptions on failure (see `device_interface.instructions.md`) — catch them all with `except Exception as e` and return `ActionFailed`:

```python
@action
def dispense_target_mass(self, target_g: float, speed_rps: float) -> dict:  # json_result あり
    try:
        self.dispenser.dispense(...)
        return ActionSucceeded(json_result={"mass_g": 1.23})
    except Exception as e:
        return ActionFailed(errors=[e])  # exception type, message, and timestamp are all recorded

@action
def move_to_position(self, position: str) -> ActionResult:  # json_result なし
    try:
        self.arm.move(position)
        return ActionSucceeded()
    except Exception as e:
        return ActionFailed(errors=[e])
```

- `json_result` in `ActionSucceeded` is used for `feed_forward` in the Workflow YAML, and is **automatically saved** to the Data Manager when run via a Workflow (see Data Saving below)
- If an unhandled exception escapes the action (e.g. a bug), the framework sets `errored = True` — the node will not accept new actions until `POST /admin/reset` is called

Admin commands are sent via `POST /admin/{command}`. Some are implemented by the framework; others must be implemented in the Node class.

| Command | NodeStatus flag | Set by | Cleared by | Must implement |
|---|---|---|---|---|
| `lock` / `unlock` | `locked` | `lock` command | `unlock` command | — (framework) |
| `reset` | `errored` | unhandled exception | `reset` command | — (framework) |
| `shutdown` | — | — | — | — (framework) |
| `pause` / `resume` | `paused` | `def pause(self)` | `def resume(self)` | ✅ |
| `safety_stop` | `stopped` | `def safety_stop(self)` | `reset` command | ✅ (optional) |

- `errored` and `stopped` both block new actions until `reset` is called


### Pause support

**Design principle:** Most device commands in this project are synchronous and block until the operation completes. Some commands (e.g. `start_rotation`) return immediately and rely on a paired command (e.g. `stop_rotation`) to terminate the operation. In both cases, the Action wrapping the command completes normally and returns `ActionSucceeded`.

```python
# Node class — implement these methods
def pause(self) -> None:
    self.node_status.paused = True

def resume(self) -> None:
    self.node_status.paused = False
```

Inside actions, insert the pause check **between** device commands:

```python
@action
def dispense_batch(self, n: int) -> ActionResult:
    for i in range(n):
        while self.node_status.paused:   # wait here until resumed
            time.sleep(0.1)
        self.dispenser.dispense(...)
    return ActionSucceeded()
```

> If a device command needs to be interrupted *during* execution (e.g., collision detection during a multi-second robot arm move), that logic belongs **inside the device command itself** — not in `pause()`. The device command should poll sensors internally and raise an exception if a threshold is exceeded.

### `safety_stop` (optional)

Implement only if the system has physical safety devices (e.g., emergency stop button):

```python
def safety_stop(self) -> None:
    # Stop all actuators immediately
    if self.dispenser is not None:
        self.dispenser._halt_and_hold()
    self.node_status.stopped = True
```

If implemented, also check `self.node_status.stopped` in action loops the same way as `paused`.

---

## Data Saving

### Automatic saving (via Workflow)

When an action is executed **via a Workflow**, the Workcell Engine automatically saves the action's return data to the Data Manager. No explicit save call is needed in the action code.

| Return field | Saved as | Label | Backend |
|---|---|---|---|
| `json_result` (dict, number, list, etc.) | `ValueDataPoint` | `"json_result"` (fixed) | MongoDB |
| `files` (`Path` or `ActionFiles` subclass) | `FileDataPoint` | file key name | MinIO or local disk |

```python
@action
def calibrate_dispenser(self, material_name: str) -> ActionSucceeded:
    try:
        result = {"g_per_rev": 0.12, "speed_ml_per_min": 2.0}
        return ActionSucceeded(json_result=result)
        # ↑ Workcell Engine saves ValueDataPoint(label="json_result", value=result) automatically
    except Exception as e:
        return ActionFailed(errors=[e])
```

The saved data is also used by `feed_forward` to pass values to subsequent Workflow steps.

> **When called outside a Workflow** (e.g. from a notebook via REST API or Swagger UI), the Workcell Engine is not involved — `json_result` is returned in the HTTP response but **not** saved to the Data Manager.

Ownership metadata is attached automatically to saved datapoints:
- `datapoint_id` — ULID, auto-generated
- `data_timestamp` — time of saving
- `ownership_info` — `experiment_id`, `campaign_id`, `workflow_id`, `step_id`, `node_id`, `workcell_id`, `user_id`, `manager_id`, `project_id`, `lab_id`

Fields that the system cannot know must be stored inside `value` (e.g. `material_name`, `pressure_mpa`).

> **Rule: include Data Manager search keys in `json_result`**
>
> When designing `json_result`, always include any field that will be needed to filter or identify
> the datapoint later in the Data Manager. The system automatically records execution context
> (timestamp, workflow/step/node IDs), but domain-specific identifiers are not captured automatically.
>
> Typical fields to include:
> - `material_name` — which material was processed
> - `pressure_mpa` — operating condition
> - Any other parameter that distinguishes this run from others of the same action type
>
> Measurement results (masses, densities, iteration counts, etc.) are included alongside these keys
> in the same flat dict — no need to separate "meta" from "results".

---

### Explicit saving (optional)

To save additional data beyond what `json_result` captures (e.g. intermediate results, detailed logs with a custom label), call one of these convenience methods inside the action:

| Method | What it does |
|---|---|
| `self.create_and_upload_value_datapoint(value=..., label=...)` | Creates a `ValueDataPoint` and uploads it to the Data Manager |
| `self.create_and_upload_file_datapoint(file_path=..., label=...)` | Creates a `FileDataPoint` and uploads it to the Data Manager |

```python
@action
def calibrate_density(self, material_name: str) -> ActionSucceeded:
    try:
        result = {"g_per_rotation": 0.12, "data_points": [...]}

        # Optional: save with a custom label (in addition to the automatic json_result save)
        self.create_and_upload_value_datapoint(
            value=result,
            label="density_calibration",
        )

        return ActionSucceeded(json_result=result)
    except Exception as e:
        return ActionFailed(errors=[e])
```

These explicit saves are independent of the automatic `json_result` save. In this project, most actions only need `json_result` — explicit saving is rarely necessary.

---

### Summary

| Scenario | What to do |
|---|---|
| Return results for workflow use and automatic persistence | `return ActionSucceeded(json_result={...})` |
| Save additional data with a custom label | `self.create_and_upload_value_datapoint(...)` |
| Return a file | `return ActionSucceeded(files=Path("/path/to/file"))` |
| Save a file with a custom label | `self.create_and_upload_file_datapoint(...)` |
