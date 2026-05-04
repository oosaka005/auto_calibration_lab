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
- For any device-specific value to display on the dashboard, define a dedicated attribute (e.g. `current_mass_g: float`) and update it inside the relevant command. Reference it explicitly in `state_handler` in the Node module.

## Connection Check (`check_status`)

Every device class must implement a `check_status(self) -> None` method. It is called by `state_handler` every ~2 seconds.

- **Purpose**: verify the physical connection and update `self.status` in real time without waiting for a command to fail.
- **On success**: optionally update cached values (e.g. `current_mass_g`). Do not change `status`.
- **On failure**: set `self.status = "disconnected"`. Do not raise — swallow the exception.
- **Busy guard (serial/hardware devices)**: use `threading.Lock` to prevent concurrent access.
  - Acquire the lock non-blocking (`self._lock.acquire(blocking=False)`).
  - If the device is busy, return immediately without changing `status`.
  - All public commands that communicate with hardware must also use `with self._lock:`.
- **SiLA devices**: call a lightweight Property (e.g. `Status`) instead. No lock needed.
- **Fake interfaces**: implement as a no-op (`pass`). Do not simulate failures here.

```python
# Serial example
def check_status(self) -> None:
    """Try a lightweight read to verify connection. Skipped if busy."""
    if not self._lock.acquire(blocking=False):
        return
    try:
        self._serial.write(b"R")
        raw = self._read_response()
        self.current_mass_g = float(raw.strip())
    except Exception:
        self.status = "disconnected"
    finally:
        self._lock.release()

# SiLA example
def check_status(self) -> None:
    """Read Status property from SiLA server to verify connection."""
    try:
        self.status = self._client.Balance.Status.get()
    except Exception:
        self.status = "disconnected"

# Fake example
def check_status(self) -> None:
    """No-op for fake interface; status is always connected."""
```

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
- File name: `{device_name}_{protocol}.py` (e.g. `balance_proprietary.py`, `balance_sila.py`)
- Class name: `{DeviceName}{Protocol}` (e.g. `BalanceProprietary`, `BalanceSila`)
- `{protocol}` reflects the connection method (e.g. `proprietary` for direct serial, `sila` for SiLA2)

### Fake interface files
- File name: `{device_name}_{protocol}_fake.py` (e.g. `balance_proprietary_fake.py`)
- Class name: `{DeviceName}{Protocol}Fake` (e.g. `BalanceProprietaryFake`)
- The fake class name is derived by appending `Fake` to the real class name (e.g. `BalanceProprietary` → `BalanceProprietaryFake`)
- Register in `DEVICE_REGISTRY` with the class name as key (e.g. `"BalanceProprietaryFake": BalanceProprietaryFake`)
- Switch between real and fake via `_class:` in `devices.settings.yaml`

## Fake Interface Rules

Follow the MADSci fake interface conventions (`docs/guides/integrator/04-fake-interfaces.md`):

- **Same API**: Method signatures (arguments and return types) must be identical to the real interface.
- **No hardware dependencies**: Do not import or instantiate `serial.Serial` or any hardware library. Set `status = "connected"` immediately in `__init__`.
- **Same argument validation**: Preserve all `ValueError`/`Exception` checks from the real interface (e.g. speed limits).
- **Same instance attributes**: Declare and update the same instance attributes as the real interface (e.g. `current_mass_g`).
- **Realistic timing**: Accept a `latency: float = 0.1` parameter in `__init__` and scale `time.sleep()` calls by it (e.g. `time.sleep(settle_time * self.latency)`).
- **Realistic data**: Return plausible values using `random.gauss()` or `random.uniform()` with a configurable base value and noise.
- **Failure simulation**: Accept a `failure_rate: float = 0.0` parameter and raise an `Exception` randomly at that probability at the start of each public method.
- **Logger**: Accept the same optional `logger` argument as the real interface.
