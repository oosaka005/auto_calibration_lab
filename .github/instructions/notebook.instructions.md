---
description: >
  Use when creating or editing Jupyter notebook files (notebooks/**/*.ipynb).
  Covers the role of notebooks in the MADSci project, MADSci client API usage,
  node action calls, resource manager access, and common import patterns for notebooks.
applyTo: "notebooks/**"
---

# Notebook Rules

## Role of notebooks/

`notebooks/` is for **human-operated work** that lives outside the automated workflow.

In MADSci, Workflow/Actions are executed automatically by the scheduler (Workcell Manager).
The following tasks that fall outside automation are done in notebooks:

| Category | Examples |
|---|---|
| **Device verification** | Connection check, individual command test (dispense/suck_back, etc.) |
| **Node Action verification** | Manually call actions via `RestNodeClient.send_action()` for testing and debugging |
| **Resource Manager registration/update** | Initial registration of material info (`attributes`), writing calibration results |
| **Data review and visualization** | Displaying calibration result graphs, etc. |

> **Alignment with MADSci design philosophy**
> MADSci treats notebooks as a human-interactive interface for lab operations.
> Both Resource Manager and Node REST APIs are directly accessible from Python clients,
> making notebooks the natural entry point for manual operations.
> Processes that should be automated belong in Workflow/Actions;
> notebooks are limited to setup, verification, and maintenance tasks.

### Existing Notebooks

| File | Role |
|---|---|
| `device_check.ipynb` | Hardware command verification for the balance (BalanceProprietary) |
| `dispenser_check.ipynb` | Hardware verification and calibration execution for the dispenser (HighViscosityDispenserProprietary) |
| `material_management.ipynb` | Registration, update, and removal of material info in the Resource Manager |

---

## MADSci Client API (v0.7.0)

### NodeClient → RestNodeClient

`NodeClient` is deprecated. Use the following to call node actions:

```python
from madsci.client.node.rest_node_client import RestNodeClient
from madsci.common.types.action_types import ActionRequest

node_client = RestNodeClient(url="http://localhost:2000/")
```

**Summary of changes:**

| Item | Old (deprecated) | New (v0.7.0) |
|---|---|---|
| Import path | `madsci.client.node_client` | `madsci.client.node.rest_node_client` |
| Class name | `NodeClient` | `RestNodeClient` |
| Constructor argument | `node_url=URL` | `url=URL` |
| Action call | `call_action(action_name=..., args=...)` | `send_action(ActionRequest(action_name=..., args=...))` |

---

### Action Call Pattern

```python
from madsci.client.node.rest_node_client import RestNodeClient
from madsci.common.types.action_types import ActionRequest

node_client = RestNodeClient(url="http://localhost:2000/")

result = node_client.send_action(
    ActionRequest(
        action_name="action_name_here",
        args={
            "param1": value1,
            "param2": value2,
        },
    )
)
print(f"Status: {result.status}")
if result.json_result:
    import json
    print(json.dumps(result.json_result, indent=2, ensure_ascii=False))
```

---

### ResourceClient

The ResourceClient import path is unchanged:

```python
from madsci.client.resource_client import ResourceClient

resource_client = ResourceClient(resource_server_url="http://localhost:8003/")
```

---

## Node Ports

| Node | Port |
|---|---|
| `high_viscosity_liquid_weighing` | `2000` |
| `human_node` | `2001` |
| Resource Manager | `8003` |

---

## Direct Device Import

When importing `devices/` classes directly from notebooks (bypassing `DEVICE_REGISTRY`):

```python
import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(os.path.abspath(".."))

def import_device(filename: str):
    path = PROJECT_ROOT / "devices" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```
