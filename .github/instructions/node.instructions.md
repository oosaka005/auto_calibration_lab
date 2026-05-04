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

Every Node file uses the following imports. Add `Path` and `FileDataPoint` only when the action generates files.

```python
import logging
import time
from pathlib import Path        # only if the action generates files
from typing import ClassVar, Optional

from madsci.common.types.action_types import ActionFailed, ActionSucceeded
from madsci.common.types.datapoint_types import FileDataPoint, ValueDataPoint  # only if using submit_datapoint()
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

### `state_handler(self) -> None`
Called automatically every ~2 seconds (`state_update_interval`). **Always read all device values** — what to display or save is a separate concern.

```python
def state_handler(self) -> None:
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

```python
@action
def dispense_target_mass(self, target_g: float, speed_rps: float) -> ActionSucceeded:
    ...

@action(blocking=False)
def get_status(self) -> ActionSucceeded:
    ...
```

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
def dispense_target_mass(self, target_g: float, speed_rps: float) -> ActionSucceeded:
    try:
        self.dispenser.dispense(...)
        return ActionSucceeded(json_result={"mass_g": 1.23})
    except Exception as e:
        return ActionFailed(errors=[e])  # exception type, message, and timestamp are all recorded
```

- `json_result` in `ActionSucceeded` is available for `feed_forward` in the Workflow YAML
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
def dispense_batch(self, n: int) -> ActionSucceeded:
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

There are two distinct data saving patterns:

| Pattern | Where stored | Lifetime | How |
|---|---|---|---|
| **Temporary** | Workcell Manager | Duration of workflow run | `ActionSucceeded(json_result=..., files=...)` |
| **Persistent** | Data Manager | Permanently | `self.data_client.submit_datapoint(...)` |

---

### Temporary: `ActionSucceeded` fields

Use these fields to pass data to the next step via `feed_forward`, or to record results in the workflow run history (the per-run log of each step's inputs and outputs stored in the Workcell Manager):

| Field | Type | When to use |
|---|---|---|
| `json_result` | Any JSON-serializable value (dict, list, number, etc.) | Measurement results, calculated values |
| `files` | `{"key": Path(...)}` | Files generated during the action |

```python
# JSON result — available for feed_forward in the Workflow YAML
return ActionSucceeded(json_result={"mass_g": 1.23})

# File result
return ActionSucceeded(files={"report": Path("/tmp/report.csv")})

# Both
return ActionSucceeded(json_result={"mass_g": 1.23}, files={"log": Path("/tmp/log.txt")})
```

---

### Persistent: `submit_datapoint()`

Saving to the Data Manager is **never automatic** — it must be called explicitly inside the Action. Each call saves one datapoint; call it multiple times to save both a value and a file.

| Class | Fields | When to use |
|---|---|---|
| `ValueDataPoint` | `label`, `value` | Any JSON-serializable value (numbers, dicts, lists) |
| `FileDataPoint` | `label`, `path` | Files generated during the action |

```python
from madsci.common.types.datapoint_types import ValueDataPoint, FileDataPoint

@action
def calibrate_density(self, ...) -> ActionSucceeded:
    result = {"g_per_rotation": 0.12, "data_points": [...]}
    log_path = Path("/tmp/calibration_log.csv")

    # Persist value to Data Manager
    self.data_client.submit_datapoint(
        ValueDataPoint(label="density_g_per_rot", value=result)
    )

    # Persist file to Data Manager (separate call)
    self.data_client.submit_datapoint(
        FileDataPoint(label="calibration_log", path=log_path)
    )

    # Also return for workflow feed_forward (Workcell Manager, temporary)
    return ActionSucceeded(json_result=result)
```

Specify only `label` and `value` (or `path`). The following are attached automatically:
- `datapoint_id` — ULID, auto-generated
- `data_timestamp` — time of saving
- `ownership_info` — `workflow_id`, `step_id`, `experiment_id`, etc., inherited from execution context

The Data Manager selects the storage backend automatically:
- `ValueDataPoint` → MongoDB
- `FileDataPoint` → MinIO (if configured), otherwise local disk
