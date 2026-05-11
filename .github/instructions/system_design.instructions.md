---
description: >
  Use when designing or reviewing the overall system architecture: Workcell, Workflow, Node,
  Action, and Device Command hierarchy. Covers design principles, granularity decisions, and
  concrete structural conventions.
applyTo: "**"
---

# System Design: MADSci Lab Automation Architecture

## Design Hierarchy

### Hardware Side

| Concept | Granularity / Definition |
|---|---|
| **Workcell** | The entire experimental system (e.g., weighing → mixing → viscosity measurement as one unified physical environment) |
| **Node** | A **process station unit**. Abstracts one or more Devices. Exposed externally via REST API |
| **Device** | A **single physical instrument** that makes up a Node (e.g., robot arm, balance, mixer) |

### Device Ownership Rule

> **One Device must be owned by exactly one Node.**

- A Node may contain multiple Devices (e.g., balance + dispenser in one Node)
- A Device must not be listed in more than one Node's `node.settings.yaml`

**Why:** Devices communicate over a physical interface (e.g., serial port). Two Node processes connecting to the same port causes a hardware conflict. MADSci provides no cross-Node device sharing mechanism.

**For complex systems:** If multiple Nodes logically need access to the same physical resource (e.g., a shared robot arm), the correct design is to give that resource its own dedicated Node and coordinate access through Workflow step ordering.

---

### Software / Execution Side

| Concept | Granularity / Definition |
|---|---|
| **Workflow** | Split at **parallel execution or re-execution boundaries**. Each workflow is independently schedulable |
| **Step** | The unit by which a Workflow invokes a Node Action. 1 Step = 1 Action call |
| **Action** | Since **Workflows have no loop syntax**, any process requiring iteration must be fully encapsulated inside an Action. Defined per Node |
| **Command** | User-defined **minimum device operation unit**. Written in Action implementation code (Python). Not an official MADSci concept |

---

## Splitting Decision Rules

### When to split Workflows
> Split at **parallel execution** or **independent re-execution** boundaries.

Example: viscosity measurement can run in parallel with the next batch's weighing → split into Workflow A and Workflow B.

### Action granularity
> Each Action should be meaningful as a single step in the Workflow step list.  
> Any loop logic must be hidden inside the Action implementation — never in the Workflow YAML.

Example: "Weigh M materials into N containers" = 1 Step (the M×N loop lives inside the Action).

### Command granularity
> The minimum operation a Device can execute.

Examples: `move_to`, `grip`, `tare`, `dispense`. Commands never appear in Workflow YAML.

---

## Concrete Structure Example

The following shows the intended full-scale system structure.
The current `auto_calibration_lab` implements a subset of this.

```
Workcell (automated experiment system)
│
├── Workflow A: sample_preparation
│     Step 1: weighing_node.weigh_all_materials()
│               └─ Internal loop: M materials × N containers
│     Step 2: weighing_node.cap_and_load_to_mixer_container()
│     Step 3: arm_node.transport_mixer_container_to_mixer()
│     Step 4: mixing_node.mix()
│     Step 5: arm_node.retrieve_and_unload_samples()
│
└── Workflow B: viscosity_measurement
      Step 1: human_node.wait_for_confirmation()
      Step 2: viscosity_node.measure_viscosity_batch()
                └─ Internal loop: N containers
```

> **Note:** The example above represents the broader target system.
> The current `auto_calibration_lab` focuses on a single-node implementation
> (`high_viscosity_liquid_weighing`) as a first step toward this architecture.

---

## File Management

### Files Managed by the User

**`compose.yaml`** — project root  
Defines all services (managers, nodes, databases). Start the entire system with `docker compose up`.

**`settings.yaml`** — project root  
Lab-wide configuration: manager URLs, node names, and Workcell node registration (`nodes:` key). Automatically discovered by walk-up file search.

**`workflows/*.workflow.yaml`** — one file per Workflow  
Workflow definitions. Naming: `{name}.workflow.yaml`.

**`modules/{node_name}/`** — one directory per Node  
Contains the Action implementation (`*.py`) and Node settings (`node.settings.yaml`).

**`devices/devices.settings.yaml`** — one file per project  
Lists all devices with their settings (port, step count, etc.).

**`devices/*.py`** — one file per physical device  
Implements device communication commands.

**`devices/__init__.py`** — device registry  
Exports `DEVICE_REGISTRY` used by node modules. All device classes (both fake and real) are imported directly. Hardware-specific libraries are guaranteed to be available because the project uses a custom Dockerfile that installs them at build time.

```python
from .balance_proprietary_fake import BalanceProprietaryFake
from .balance_proprietary import BalanceProprietary

DEVICE_REGISTRY: dict[str, type] = {
    "BalanceProprietaryFake": BalanceProprietaryFake,
    "BalanceProprietary": BalanceProprietary,
}
```

**`devices/requirements.txt`** — device library dependencies  
Lists hardware-specific Python libraries (e.g. `pyserial`, `sila2`). Installed automatically during Docker image build via the project `Dockerfile`. When adding a device that requires a new library, add it here and run `docker compose build`.

**`Dockerfile`** — project root  
Extends the MADSci base image (`ghcr.io/ad-sdl/madsci:latest`) by installing `devices/requirements.txt`. This ensures all device libraries are available in the container.

**Dockerfile rules:**
- The base image uses a virtualenv at `/home/madsci/MADSci/.venv` (created by `uv`, not `pip`). The entrypoint activates this virtualenv at runtime.
- Libraries MUST be installed into this virtualenv. Use `uv pip install --python /home/madsci/MADSci/.venv/bin/python`. Do NOT use plain `pip install` (that installs to system Python, which is not used at runtime).
- Template:
  ```dockerfile
  FROM ghcr.io/ad-sdl/madsci:latest
  COPY devices/requirements.txt /tmp/device-requirements.txt
  RUN uv pip install --python /home/madsci/MADSci/.venv/bin/python \
      -r /tmp/device-requirements.txt && \
      rm /tmp/device-requirements.txt
  ```
- This pattern applies to any MADSci-based project, not just this one.

**Experimental condition file (manual)** — anywhere on the local PC  
Input files created by hand and passed in via `file_inputs` at submission time. Temporarily held by the Workcell Manager for the duration of the Step, then discarded.

**Device location definitions** — `settings.yaml` → `locations:` → Location Manager  
Target coordinates for robot arms etc. Updated by editing the file and restarting the Location Manager (or via REST API for dynamic updates).

---

### Data Managed Automatically by the System

**Experimental condition file (auto-generated)** → Data Manager (MongoDB / MinIO)  
Condition parameters produced by the Experiment Application. Saved only when `submit_datapoint()` is called explicitly.

**Experimental data (values)** → Data Manager (MongoDB)  
Saved only when `submit_datapoint()` is called explicitly inside an Action.

**Experimental data (files)** → Data Manager (MinIO / local disk)  
Same as above. Backend is selected automatically by the Data Manager.

**Event logs** → Event Manager (MongoDB)  
Recorded automatically by the system.

**Experiment / campaign records** → Experiment Manager (MongoDB)  
Saved automatically when using the Experiment Application.

**Workflow run history** → Workcell Manager (MongoDB)  
Recorded automatically by the system.

**Resource information (containers, reagents, etc.)** → Resource Manager (PostgreSQL)  
Only relevant when the Resource Manager is in use.
