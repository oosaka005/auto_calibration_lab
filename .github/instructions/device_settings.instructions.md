---
description: "Use when editing device settings files or node settings files. Covers how to add/remove devices per node using devices.settings.yaml and node.settings.yaml."
applyTo: "devices/**,modules/**/node.settings.yaml"
---

# Device Settings Rules

## File Roles

- `devices/devices.settings.yaml` — shared across all nodes. Defines all available devices and their connection settings.
- `modules/<node>/node.settings.yaml` — per-node. Specifies which devices this node uses.

## Name Correspondence

```
DEVICE_REGISTRY key  ←→  _class value in devices.settings.yaml
section name in devices.settings.yaml  ←→  entry in node.settings.yaml devices list
```

## Adding a Device to a Node

1. Add a section to `devices/devices.settings.yaml`:
   ```yaml
   new_device:
     _class: NewDevice   # must match a key in DEVICE_REGISTRY
     port: null
     # add other __init__ parameters here
   ```
2. Add the section name to the target node's `node.settings.yaml`:
   ```yaml
   devices:
     - existing_device
     - new_device   # must match the section name in devices.settings.yaml
   ```
3. Restart the node.

No code changes are needed. Config fields, Node attributes, startup, and shutdown are all handled automatically.

## Removing a Device from a Node

Remove the entry from `node.settings.yaml` devices list and restart the node.
The `devices.settings.yaml` section can remain (other nodes may use it).

## Notes

- `_class` must exactly match a key in `devices/__init__.py DEVICE_REGISTRY`.
- The `devices:` list in `node.settings.yaml` must exactly match section names in `devices.settings.yaml`.
- Do not remove a section from `devices.settings.yaml` unless no node uses it.

## Switching Between Real and Fake Interfaces

### Global switch (all devices at once)

Set `interface_type` in `node.settings.yaml`:

```yaml
interface_type: fake   # "fake" or "real"
```

- `"fake"` — all devices use their `FakeInterface` class (no hardware required)
- `"real"` — all devices use their real `Interface` class
- Default is `"real"` when omitted

### Per-device override

Uncomment `_interface_type` in the relevant device section in `devices.settings.yaml`:

```yaml
balance:
  _class: BalanceInterface
  # _interface_type:   # commented out → follows node-level interface_type

high_viscosity_dispenser:
  _class: HighViscosityDispenserInterface
  _interface_type: real   # overrides node-level interface_type for this device only
```

- Per-device `_interface_type` takes precedence over the node-level `interface_type`.
- `_class` always refers to the **real** interface class. The fake class is resolved automatically by replacing `Interface` with `FakeInterface` in the class name.
- Warning: mixing `"real"` and `"fake"` in a closed-loop action (e.g. dispense-by-weight) will cause incorrect behaviour. Use with care.

### How the class is resolved (in `_build_device_classes`)

```
effective_type = _interface_type (device) if set, else interface_type (node)

if effective_type == "fake":
    class = DEVICE_REGISTRY["{ClassName}".replace("Interface", "FakeInterface")]
else:
    class = DEVICE_REGISTRY["{ClassName}"]
```
