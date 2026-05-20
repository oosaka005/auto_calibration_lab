---
description: >
  Use when creating or editing experiment script files in experiments/.
  Covers ExperimentScript structure, ExperimentDesign fields, client usage,
  entry point conventions, return value handling, and MADSci concept hierarchy.
applyTo: "experiments/**"
---

# Experiments — Project Rules

## Overview

The `experiments/` folder contains campaign execution scripts that subclass `ExperimentScript`.
One file = one type of experiment campaign.

Run an experiment script with:

```bash
python experiments/calibration_campaign.py
```

---

## MADSci Concept Hierarchy

Understand the relationship between MADSci terms and files before writing `experiments/` code.

```
ExperimentalCampaign   = A label that groups multiple Experiment Runs (optional; not used in the current project)
  └── Experiment Run   = One execution of ExperimentScript.main()
                         → Start/end/status are automatically recorded in the Experiment Manager
        └── Workflow   = One call to start_workflow() (one workflow.yaml)
                         → Full step execution records are automatically saved in the Workcell Manager
```

A Python script like `calibration_campaign.py` = an **Experiment Run** in MADSci terminology.
The word "campaign" in the filename is a human-facing convention; it is not the same as `ExperimentalCampaign`.

---

## Required Structure Pattern

```python
from madsci.common.types.experiment_types import ExperimentDesign
from madsci.experiment_application.experiment_script import ExperimentScript


class MyCampaign(ExperimentScript):

    # (1) Define experiment metadata as a class attribute (required)
    experiment_design = ExperimentDesign(
        experiment_name="Dispenser Calibration Campaign",
        experiment_description=(
            "Calibrate the high-viscosity dispenser for each registered material "
            "and verify gravimetric accuracy across multiple target masses."
        ),
    )

    # (2) Write experiment logic here (required; method name is fixed)
    def run_experiment(self) -> dict:
        results = {}
        for params in MATERIALS:
            workflow = self.workcell_client.start_workflow(
                WORKFLOW_PATH,
                json_inputs=params,
            )
            results[params["material_name"]] = {
                "workflow_id": workflow.workflow_id,
                "status": str(workflow.status),
            }
        return results


# (3) Entry point (required)
if __name__ == "__main__":
    MyCampaign.main()
```

---

## Class Design Rules

| Rule | Detail |
|---|---|
| Inheritance | Must subclass `ExperimentScript` |
| `experiment_design` | Must be defined as a class attribute |
| `run_experiment()` | **Method name is fixed.** Called internally by `run()`. Do not rename. |
| One class = one procedure | Place loops over multiple materials etc. **inside** `run_experiment()`. Do not split into multiple classes. |

---

## `ExperimentDesign` Fields (all)

```python
from madsci.common.types.experiment_types import ExperimentDesign
from madsci.common.types.auth_types import OwnershipInfo

ExperimentDesign(
    # --- Required ---
    experiment_name="Dispenser Calibration Campaign",

    # --- Optional ---
    experiment_description=(
        "Calibrate the high-viscosity dispenser for each registered material."
    ),

    # --- Optional; not used in the current project ---
    # Defines resource conditions that must be satisfied before the experiment starts.
    # Use in the future when a robot arm is introduced (e.g., "sample must be placed at location X").
    resource_conditions=[],   # default: []

    # --- Optional; resolved automatically from settings.yaml if omitted ---
    # Set explicitly only when grouping multiple Experiment Runs under an ExperimentalCampaign.
    # Not used in the current project.
    # ownership_info=OwnershipInfo(
    #     campaign_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
    # ),
)
```

---

## Entry Point

**Use `main()` by default.**

```python
if __name__ == "__main__":
    MyCampaign.main()
```

How `main()` works internally:

```python
# ExperimentScript.main() (simplified)
@classmethod
def main(cls, experiment_design=None, lab_server_url=None, *args, **kwargs):
    instance = cls(                        # creates an instance (same as CalibrationCampaign())
        experiment_design=experiment_design,
        lab_server_url=lab_server_url,
    )
    return instance.run(*args, **kwargs)   # calls run()
```

Inside `run()`, `manage_experiment()` is called automatically, which records experiment start/end/failure in the Experiment Manager.

> **Note:** Calling `instance.run()` directly is also possible but is limited to special cases (e.g., dynamically setting the URL in code, calling from test code). Use `main()` in normal situations.

---

## Available Clients

`ExperimentScript` inherits `MadsciClientMixin`, which makes clients for each manager available automatically as `self.xxx_client`. URLs are resolved automatically via walk-up discovery from `settings.yaml`.

| Client (`self.xxx_client`) | Manager | Port |
|---|---|---|
| `workcell_client` | Workcell Manager | 8005 |
| `data_client` | Data Manager | 8004 |
| `experiment_client` | Experiment Manager | 8002 |
| `resource_client` | Resource Manager | 8003 |
| `location_client` | Location Manager | 8006 |
| `logger` | Event Manager (logging) | 8001 |

In `experiments/`, primarily use `workcell_client` and `logger`.
`experiment_client` is called internally by `manage_experiment()` and rarely needs to be used directly.

---

## Workflow Execution

### `workcell_client.start_workflow()`

```python
workflow = self.workcell_client.start_workflow(
    WORKFLOW_PATH,           # path to workflow.yaml (str or Path)
    json_inputs=params,      # dict passed to the workflow's parameters
    # await_completion=True  # default True: automatically waits until the workflow finishes
    # prompt_on_error=True   # default True: prompts in the terminal on error
)
```

Because `await_completion=True` is the default, **no manual wait code is needed**.
The Workcell Manager also handles step ordering automatically, so no wait code between steps is required.

### Workcell Manager Scheduling

The current implementation is FIFO-based. The following are handled automatically:
- If a node is busy (running a previous Action), waits until it finishes
- Checks for location and resource availability
- Manages step execution order

When multiple workflows are queued simultaneously, execution order can be controlled with `priority` (integer).
In the typical case of submitting one workflow at a time, `priority` does not need to be specified.

### `workcell_client` Main Methods

| Method | Description |
|---|---|
| `start_workflow(path, json_inputs, ...)` | Execute a workflow (waits for completion by default). Returns a `Workflow` object. |
| `submit_workflow_sequence([path1, path2, ...])` | Execute multiple workflows in sequence |
| `submit_workflow_batch([path1, path2, ...])` | Execute multiple workflows in parallel |
| `pause_workflow(id)` / `resume_workflow(id)` | Pause and resume a running workflow externally (e.g., emergency stop). For declarative human-in-the-loop steps, use `human_node` instead. |
| `cancel_workflow(id)` | Cancel a workflow |
| `retry_workflow(id)` | Re-run a failed workflow |

### `Workflow` Object (return value of `start_workflow()`)

An execution record of a completed workflow. Used to access step results and datapoints.

| Field / Method | Description |
|---|---|
| `workflow_id` | Execution ID (ULID) |
| `status` | Execution status (completed / failed, etc.) |
| `get_datapoint(step_key, label)` | Get a Datapoint object saved by a step |
| `get_datapoint_id(step_key, label)` | Get only the ID of a Datapoint |
| `get_step_by_key(key)` | Get a step object |
| `duration_seconds` | Execution time in seconds |

---

## Return Value of `run_experiment()`

**Information automatically recorded by MADSci (independent of the return value):**

| Destination | Automatically saved content |
|---|---|
| Experiment Manager | experiment_id, start time, end time, status (completed/failed) |
| Workcell Manager | Full records of each workflow run (workflow_id, step results, timestamps) |
| Data Manager | Data explicitly saved by a Node Action via `submit_datapoint()` |

**How to use the return value of `run_experiment()`:**
It is not automatically saved by MADSci. Use it to return information the human running the script wants to see in the console.
The recommended pattern is to return a dict containing traceability information such as `workflow_id`.

```python
def run_experiment(self) -> dict:
    results = {}
    for params in MATERIALS_TO_CALIBRATE:
        material_name = params["material_name"]
        workflow = self.workcell_client.start_workflow(
            WORKFLOW_PATH, json_inputs=params
        )
        self.logger.info(f"Workflow completed: {material_name}")
        results[material_name] = {
            "workflow_id": workflow.workflow_id,
            "status": str(workflow.status),
        }
    self.logger.info("Campaign complete.")
    return results
```

---

## Logging

```python
self.logger.info(f"Starting calibration for: {material_name}")
self.logger.warning("Something unexpected but non-fatal")
self.logger.error("Something failed")
```

Logs are automatically sent to the Event Manager and can be viewed via the Dashboard or Swagger UI.

---

## `ExperimentalCampaign` and `register_campaign.py`

### What is ExperimentalCampaign?

A container for recording the theme of a campaign — i.e., what kind of experiments are being run.
Examples: "Improving thermal properties of thermal grease", "Evaluating dispersion stability of new materials"

The purpose is to **group related Experiment Runs under a single `campaign_id`**.

| Field | Description |
|---|---|
| `campaign_id` | Auto-generated ULID |
| `campaign_name` | Campaign theme name (required) |
| `campaign_description` | Detailed description (optional) |
| `experiment_ids` | List of linked Experiment Run IDs (managed automatically) |

> `ExperimentalCampaign` cannot hold experiment parameters or optimization settings. It is purely a label / grouping mechanism.

---

### `register_campaign.py`

`experiments/register_campaign.py` — **a one-time setup script for registering a campaign**.
Run once before starting a new experiment theme to obtain a `campaign_id`, then record it in the experiment script.

```python
from madsci.client.experiment_client import ExperimentClient
from madsci.common.types.experiment_types import ExperimentalCampaign

CAMPAIGN_NAME = "Enter campaign name here"
CAMPAIGN_DESCRIPTION = """
Enter description here.
"""
EXPERIMENT_MANAGER_URL = "http://localhost:8002/"

if __name__ == "__main__":
    ec = ExperimentClient(experiment_server_url=EXPERIMENT_MANAGER_URL)
    campaign = ec.register_campaign(ExperimentalCampaign(
        campaign_name=CAMPAIGN_NAME,
        campaign_description=CAMPAIGN_DESCRIPTION.strip(),
    ))
    campaign_id = campaign["campaign_id"]
    print(f"Campaign registered successfully.")
    print(f'  campaign_id = "{campaign_id}"')
    print(f"Set this in your experiment script's ExperimentDesign.ownership_info.")
```

### Using the obtained `campaign_id`

```python
from madsci.common.types.auth_types import OwnershipInfo

class MyCampaign(ExperimentScript):
    experiment_design = ExperimentDesign(
        experiment_name="...",
        ownership_info=OwnershipInfo(
            campaign_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",  # set here
        ),
    )
```

Setting `campaign_id` links this Experiment Run to the campaign in the Experiment Manager.
If grouping is not needed, this field can be omitted and the experiment will still run normally.
