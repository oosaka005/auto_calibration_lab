---
description: "Use when creating or editing device interface files in modules/devices/. Covers structure, command conventions, error handling, status, logging rules, and fake interface conventions."
applyTo: "modules/devices/**"
---

# Device Interface Rules

## Structure

- Open the connection in `__init__`; close it in `close()`.
- Internal helper methods must have a `_` prefix (e.g. `_send_command()`).
- Public commands have no prefix (e.g. `tare()`, `read_weight()`).

## Command Conventions

- Name commands after the device function they perform (verb-based).
- Commands must block until the operation is complete (no async).
- Add type hints to all parameters (`int`, `float`, `str`, `bool`, `Enum`, `Optional[T]`, etc.).
- Provide default values where applicable (e.g. `amount: float = 5.0`).
- Annotate return types when a value is returned (e.g. `-> float`).
- Write a one-line docstring on the line immediately after the `def` line (e.g. `"""Read current mass."""`).

## Error Handling

- Raise an `Exception` (or subclass) on failure. This is the sole mechanism by which the upper layer detects errors.

## Status

- Every device class must have a `status: str` attribute with value `"connected"` or `"disconnected"`.
- Set `status = "connected"` at the end of `__init__`; set `status = "disconnected"` in `close()`.
- Any value intended for dashboard display should be stored as an instance attribute and updated whenever the relevant command is called.

## Logger

- Accept an optional `logger` argument in `__init__`. Fall back to `logging.getLogger(__name__)` when omitted.
- MADSci loggers conform to the Python standard `logging.Logger` interface, so `.info()` etc. work identically for both.
- Pass only a plain `message` string to the logger — never `**kwargs`. This preserves compatibility with the standard logger.
- Log only normal, non-exceptional events (e.g. connect, disconnect). Do not log raised exceptions; the upper layer (MADSci, etc.) records them automatically.

## Registration

- After creating a new device class, add an entry to `DEVICE_REGISTRY` in `devices/__init__.py`:
  ```python
  from .my_device import MyDevice

  DEVICE_REGISTRY: dict[str, type] = {
      ...
      "MyDevice": MyDevice,
  }
  ```
- The key must be the class name exactly as it will be written in `devices.settings.yaml` under `_class:`.
- Without this entry the node cannot resolve the class from the settings file.

## Naming Conventions

### Real interface files
- File name: `{device_name}_interface.py` (e.g. `balance_interface.py`)
- Class name: `{DeviceName}Interface` (e.g. `BalanceInterface`)

### Fake interface files
- File name: `{device_name}_fake_interface.py` (e.g. `balance_fake_interface.py`)
- Class name: `{DeviceName}FakeInterface` (e.g. `BalanceFakeInterface`)
- Register in `DEVICE_REGISTRY` with the class name as key (e.g. `"BalanceFakeInterface": BalanceFakeInterface`)
- Switch between real and fake via `_class:` in `devices.settings.yaml`

## Fake Interface Rules

Follow the MADSci fake interface conventions (`docs/guides/integrator/04-fake-interfaces.md`):

- **Same API**: Method signatures (arguments and return types) must be identical to the real interface.
- **No hardware dependencies**: Do not import or instantiate `serial.Serial` or any hardware library. Set `status = "connected"` immediately in `__init__`.
- **Same argument validation**: Preserve all `ValueError`/`Exception` checks from the real interface (e.g. speed limits).
- **Same instance attributes**: Declare and update the same instance attributes as the real interface (e.g. `current_mass_g`, `motion_status`).
- **Realistic timing**: Accept a `latency: float = 0.1` parameter in `__init__` and scale `time.sleep()` calls by it (e.g. `time.sleep(settle_time * self.latency)`).
- **Realistic data**: Return plausible values using `random.gauss()` or `random.uniform()` with a configurable base value and noise.
- **Failure simulation**: Accept a `failure_rate: float = 0.0` parameter and raise an `Exception` randomly at that probability at the start of each public method.
- **Logger**: Accept the same optional `logger` argument as the real interface.
