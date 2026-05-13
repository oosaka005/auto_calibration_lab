---
description: >
  Use when creating or editing workflow YAML files. Covers file naming, directory structure,
  YAML schema, parameter types, step key conventions, and ID generation rules.
applyTo: "workflows/**"
---

# Workflow File Rules

## File Conventions

- **One workflow per file**
- **Naming**: `{name}.workflow.yaml` (e.g., `calibration.workflow.yaml`)
- **Location**: `workflows/` directory

---

## YAML Schema

```yaml
name: human_readable_workflow_name          # Required. Workflow identifier.

metadata:                                   # Optional.
  author: Your Name
  description: What this workflow does
  version: 1.0

parameters:                                 # Optional. Inputs from outside the workflow.
  json_inputs:
    - key: param_name
      description: What this parameter controls
      default: 1.0                          # Optional default value
  file_inputs:
    - key: file_param_name
  feed_forward:                             # Pass a prior step's output as input to a later step.
    - key: feed_param_name
      step: prior_step_key
      data_type: json                       # or: file

steps:                                      # Required. List of steps.
  - name: Human-readable step name         # Display name.
    key: unique_step_key                    # Optional but recommended. Snake_case. Must be unique within the workflow.
    node: target_node_name                  # The node to call. Omit for built-in workcell actions.
    action: action_name                     # The action to invoke.
    args:                                   # Arguments passed to the action.
      param_name: value
    description: "Optional step description"
```

---

## Parameter Types

### `json_inputs`

JSON values (numbers, strings, booleans, etc.) passed in from outside at submission time. Parameters without a `default` are required — omitting them raises an error. Common ways to supply them:

- **Squid Dashboard**: enter values in the browser UI before running
- **Python client**: pass as `json_inputs={...}` when calling `WorkcellClient.start_workflow()`
- **Experiment Application**: retrieve previous results from the Data Manager and pass them in programmatically

```yaml
parameters:
  json_inputs:
    - key: target_mass_g
      description: Target dispense mass in grams       # required (no default)
    - key: speed_rps
      description: Dispenser speed in rotations/sec
      default: 1.5                                     # optional
```

### `file_inputs`

For passing an actual file (CSV, image, binary, etc.) as input — use this when the data cannot be expressed as an inline JSON value. Most inputs should use `json_inputs` instead. Declared as named slots in the YAML; the matching local path is supplied at submission time. Note: files in MinIO cannot be referenced directly — download to the local machine first.

```yaml
# Workflow definition — declare the slot
parameters:
  file_inputs:
    - key: calibration_data
      description: CSV file with calibration reference data
```

```python
# Submission — supply a local path matching the key
workcell_client.start_workflow(
    workflow,
    file_inputs={"calibration_data": Path("/home/user/data/calibration.csv")},
)
```

### `feed_forward`

A named slot that captures a prior step's output datapoint and injects it as input into a later step — effectively a temporary relay that passes data between steps without external storage. Requires `step` (key of the source step) and `data_type`. The source step must call `submit_datapoint()` for the value to be available.

```yaml
parameters:
  feed_forward:
    - key: density_result
      step: calibrate_density     # key of the step that produced this value
      data_type: json             # or: file, object_storage
```

### Referencing parameters in steps

Use `use_parameters:` to map workflow parameters into a step's fields:

```yaml
steps:
  - key: my_step
    node: my_node
    action: my_action
    use_parameters:
      args:
        action_arg_name: workflow_param_key
```

---

## Step Rules

### `name` (Required)
Human-readable display name for the step. Shown in the Squid Dashboard and logs.

### `key` (Required)
A short snake_case identifier for the step.
- Must be unique within the workflow
- Referenced by `feed_forward` parameters via `step: {key}` and by `data_labels`
- **Naming rule:** Use the `action` name as-is (e.g., `key: calibrate_speed` when `action: calibrate_speed`). This ensures that the same action produces datapoints with a consistent `step_id` across different workflows, enabling cross-workflow comparison via the Data Manager.
- **Exception:** When the same action appears more than once in a workflow, append a sequential number: `{action}_{n}` (e.g., `tare_1`, `tare_2`).

### `action` (Required)
The name of the Action to invoke on the target Node.

### `node` (Required)
The name of the Node to call. Must match a key in `settings.yaml` → `nodes:`.

### `args` (Optional)
Key-value pairs passed directly to the Action as arguments. Values can be literals or mapped from workflow parameters via `use_parameters`.

### `files` (Optional)
File arguments passed to the Action. Maps argument name to a `file_inputs` parameter key.
```yaml
files:
  input_csv: calibration_data    # maps to file_inputs key
```

### `locations` (Optional)
Location arguments for robot arm movements etc. Maps argument name to a location name defined in `settings.yaml` → `locations:`.
```yaml
locations:
  target_position: container_slot_1
```

### `conditions` (Optional)
A list of conditions that must be met before the step is executed. Used for conditional execution logic (e.g., wait for a resource to be available).

### `data_labels` (Optional)
Maps the names of datapoints produced by the Action to custom label names. Used in combination with `feed_forward`'s `label:` field to identify specific outputs from a step.
```yaml
data_labels:
  density_g_per_ml: density_result    # Action output name → label used by feed_forward
```

### `use_parameters` (Optional)
Maps workflow-level parameters into this step's fields. See the "Referencing parameters in steps" section above.

> **Note:** The rules above apply to steps that call a Node action. For built-in Workcell actions (`wait`, `transfer`, `transfer_resource`), `node` is omitted. Arguments are passed via `args` as usual.
> - `wait`: `args: {seconds: 30}`
> - `transfer`: `args: {source: location_a, target: location_b}` — the Location Manager resolves which Node handles the move
> - `transfer_resource`: `args: {resource_id: <id>, target: location_b}` — the Resource Manager locates the resource first

---

## Example: this project's workflows

```
workflows/
  calibration.workflow.yaml         # Calibrate density and speed
  dispensing.workflow.yaml          # Dispense to a target mass
  weighing_accuracy_test.workflow.yaml  # End-to-end accuracy verification
```
