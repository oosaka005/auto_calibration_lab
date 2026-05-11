---
description: "Use when creating or editing device interface files in modules/devices/. Covers structure, command conventions, error handling, status, logging rules, and fake interface conventions."
applyTo: "modules/devices/**"
---

# Device Interface Rules

## Structure

- Open the connection in `__init__`; close it in `close()`.
- Internal helper methods must have a `_` prefix (e.g. `_send_command()`).
- Public commands have no prefix (e.g. `tare()`, `read_weight()`).

## Connection Patterns

There are currently two connection patterns. Define the `__init__` signature corresponding to each pattern. All parameter values required for connection must be managed in `devices.settings.yaml` and must not be hardcoded.

### Pattern 1: Serial Communication (Proprietary)

Communicates directly with the device via a serial interface such as UART or RS-232. Uses pyserial's `serial.serial_for_url`.

Parameters to define in `__init__`:
- `port: str` — serial port path on the RPi (e.g. `/dev/ttyAMA0` on RPi5; `/dev/serial0` on RPi4)
- `baud_rate: int` — baud rate
- `host: Optional[str]` — IP address of the RPi. If set, connects via ser2net over raw TCP (`socket://`).
- `ser2net_port: int` — TCP port number exposed by ser2net. Assign a unique number per device on the same RPi.

**Connection rules:**
- Always use `serial.serial_for_url()`, never `serial.Serial()`. `serial_for_url()` handles both URL schemes (`socket://`, `rfc2217://`) and local port names (`COM3`, `/dev/ttyAMA0`).
- Use `socket://` (not `rfc2217://`) when ser2net is configured with `accepter: tcp`. The baud rate is fixed in ser2net's `connector` line and does not need to be negotiated.
- Use `rfc2217://` only when ser2net is configured with `accepter: telnet(rfc2217)`.

```python
def __init__(
    self,
    port: str,
    baud_rate: int = 9600,
    host: Optional[str] = None,
    ser2net_port: int = 2217,
    logger: Optional[logging.Logger] = None,
) -> None:
    # socket:// for raw TCP (ser2net tcp mode). Baud rate is set in ser2net config.
    serial_port = f"socket://{host}:{ser2net_port}" if host else port
    self._serial = serial.serial_for_url(serial_port, baud_rate, timeout=1.0)
```

RPi-side requirements:
- Install ser2net and append a connection definition to `/etc/ser2net.yaml`:
  ```yaml
  connection: &<device_name>
    accepter: tcp,<ser2net_port>
    connector: serialdev,<serial_port>,<baud_rate>n81,local
    options:
      kickolduser: true
  ```
- Enable auto-start with `sudo systemctl enable --now ser2net`.

---

### Pattern 2: SiLA2 (Sila)

The SiLA2 server handles the physical connection to the device and exposes it over gRPC. Uses `sila2.client.SilaClient`. Unlike Pattern 1, the node can run on the PC since the physical connection is managed by the SiLA2 server.

Parameters to define in `__init__`:
- `host: str` — IP address of the host running the SiLA2 server
- `sila_port: int` — SiLA2 server port number (default: 50052)
- `insecure: bool` — set to `True` to disable TLS (use `True` in development environments)

```python
def __init__(
    self,
    host: str,
    sila_port: int = 50052,
    insecure: bool = True,
    logger: Optional[logging.Logger] = None,
) -> None:
    self._client = SilaClient(address=host, port=sila_port, insecure=insecure)
```

RPi-side requirements:
- Register the SiLA2 server as a systemd service and enable it:
  ```ini
  [Unit]
  Description=<Device> SiLA2 Server
  After=network.target

  [Service]
  Type=simple
  User=<user>
  WorkingDirectory=<path/to/server>
  ExecStart=<path/to/.venv/bin/python> -m <server_module> --ip-address 0.0.0.0 --port <sila_port> --insecure
  Restart=on-failure
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
- `--ip-address 0.0.0.0` is required to accept connections from external hosts.

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

- After creating a new device class, add an import and an entry to `DEVICE_REGISTRY` in `devices/__init__.py`:
  ```python
  from .my_device import MyDevice

  DEVICE_REGISTRY: dict[str, type] = {
      ...
      "MyDevice": MyDevice,
  }
  ```
- The key must be the class name exactly as it will be written in `devices.settings.yaml` under `_class:`.
- Without this entry the node cannot resolve the class from the settings file.
- Import all device classes **directly** (no `try/except ImportError`). All required libraries are guaranteed to be available in the Docker image.

## Library Management

Hardware-specific libraries (e.g. `pyserial`, `sila2`) are managed centrally:

| File | Role |
|---|---|
| `devices/requirements.txt` | Single source of truth for device libraries |
| `Dockerfile` | Extends the MADSci base image by `pip install -r devices/requirements.txt` |
| `compose.yaml` | Uses `build: .` to build the project-specific image |

**When adding a device that requires a new library:**
1. Add the library to `devices/requirements.txt`.
2. Rebuild the image: `docker compose build`.

**Do NOT:**
- Wrap imports in `try/except ImportError` — all libraries are installed at image build time.
- Install libraries at container startup (e.g. in `command:`) — this is slow and unreliable.
- Hardcode library versions unless a specific version is required for compatibility.

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
- **No hardware dependencies**: Do not import or instantiate `serial.serial_for_url` or any hardware library. Set `status = "connected"` immediately in `__init__`.
- **Same argument validation**: Preserve all `ValueError`/`Exception` checks from the real interface (e.g. speed limits).
- **Same instance attributes**: Declare and update the same instance attributes as the real interface (e.g. `current_mass_g`).
- **Realistic timing**: Accept a `latency: float = 0.1` parameter in `__init__` and scale `time.sleep()` calls by it (e.g. `time.sleep(settle_time * self.latency)`).
- **Realistic data**: Return plausible values using `random.gauss()` or `random.uniform()` with a configurable base value and noise.
- **Failure simulation**: Accept a `failure_rate: float = 0.0` parameter and raise an `Exception` randomly at that probability at the start of each public method.
- **Logger**: Accept the same optional `logger` argument as the real interface.
