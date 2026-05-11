"""Serial interface for the Pololu Tic T500 stepper motor controller.

Reference: https://www.pololu.com/docs/0J71
Serial command protocol is used (not native USB).

--- Wiring (Raspberry Pi 5) ---

    GPIO14 (pin 8,  TX) --> Tic RX
    GPIO15 (pin 10, RX) <-- Tic TX
    GND    (pin 6)      --> Tic GND
    port = "/dev/ttyAMA0"
    Enable the serial port via raspi-config:
        Interface Options -> Serial Port -> login shell: No, hardware enabled: Yes

    RPi5-specific setup required (RPi4 raspi-config alone is insufficient):
        /boot/firmware/config.txt:
            dtoverlay=uart0-pi5     # RPi5: maps UART0 to GPIO14/15 (replaces dtparam=uart0=on)
            dtoverlay=disable-bt    # detach Bluetooth from GPIO14/15
        systemd service (uart0-gpio-setup.service):
            sets GPIO14/15 to ALT4 (UART) on boot

--- Tic Control Center (one-time USB setup) ---

    - Control mode: Serial / I2C / USB
    - Command timeout: disabled  (required for dispensing longer than 1 s)
    - Baud rate: 9600            (must match baud_rate parameter)
    - Step mode: match microstep_multiplier  (T500 supports full / 1/2 / 1/4 / 1/8)
"""

import logging
import threading
import time
from typing import Optional

import serial


class HighViscosityDispenserProprietary:
    """Serial interface for the Pololu Tic T500 stepper motor controller."""

    MAX_SPEED_RPS: float = 2.0                                             # eco-PEN450 hardware limit: 120 RPM (internal use)
    MAX_SPEED_ML_PER_MIN: float = 6.0                                      # eco-PEN450 hardware limit: 6.0 mL/min
    MIN_SPEED_ML_PER_MIN: float = 0.5                                      # eco-PEN450 minimum stable speed
    MIN_VOLUME_ML: float = 0.004                                           # eco-PEN450 minimum meaningful movement volume
    _ML_PER_REV: float = 0.05                                              # eco-PEN450 fixed displacement: 0.05 mL/rev
    _MIN_ROTATIONS: float = MIN_VOLUME_ML / _ML_PER_REV                    # = 0.08 rev (internal use)
    _MIN_SPEED_RPS: float = (MIN_SPEED_ML_PER_MIN / 60.0) / _ML_PER_REV   # ≈ 0.167 rps (internal use)

    def __init__(
        self,
        port: str,
        full_steps_per_rev: int,
        microstep_multiplier: int,
        purge_speed_rps: Optional[float] = None,
        baud_rate: int = 9600,
        host: Optional[str] = None,
        ser2net_port: int = 2217,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        if purge_speed_rps is not None and purge_speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"purge_speed_rps {purge_speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
        self._lock = threading.Lock()
        self._full_steps_per_rev = full_steps_per_rev
        self._microstep_multiplier = microstep_multiplier
        self._purge_speed_rps = purge_speed_rps
        # If host is set, connect via ser2net (raw TCP) over the network.
        # ser2net's accepter uses tcp mode, so we use socket:// (not rfc2217://).
        # Baud rate is configured in ser2net's connector line, not negotiated here.
        # Otherwise, connect directly to the local serial port.
        serial_port = f"socket://{host}:{ser2net_port}" if host else port
        self._serial = serial.serial_for_url(serial_port, baud_rate, timeout=1.0)
        # Reset → reload EEPROM settings, then bring up to operable state.
        self._serial.write(b"\xb0")  # Reset (0xB0)
        time.sleep(0.01)             # Wait ≥10 ms for reset to complete
        self._energize()
        self._exit_safe_start()
        self.status = "connected"
        self._logger.info(f"HighViscosityDispenser: connected on {serial_port}")

    def _energize(self) -> None:
        """Energize the motor coils (command 0x85)."""
        self._serial.write(b"\x85")

    def _deenergize(self) -> None:
        """De-energize the motor coils (command 0x86)."""
        self._serial.write(b"\x86")

    def _exit_safe_start(self) -> None:
        """Exit safe-start condition (command 0x83)."""
        self._serial.write(b"\x83")

    def _enter_safe_start(self) -> None:
        """Enter safe-start condition, stopping the motor (command 0x8F)."""
        self._serial.write(b"\x8f")

    def _set_target_velocity(self, velocity: int) -> None:
        """Set target velocity in 0.0001 microsteps/s (command 0xE3, Tic 32-bit serial encoding)."""
        raw = velocity.to_bytes(4, byteorder="little", signed=True)
        msbs = sum((1 << i) for i, byte in enumerate(raw) if byte & 0x80)
        payload = bytes([msbs]) + bytes([byte & 0x7F for byte in raw])
        self._serial.write(b"\xe3" + payload)

    def _rps_to_tic_velocity(self, speed_rps: float) -> int:
        """Convert rev/s to Tic T500 velocity units (0.0001 microsteps/s)."""
        return int(speed_rps * self._full_steps_per_rev * self._microstep_multiplier * 10000)

    def _halt_and_hold(self) -> None:
        """Stop motion immediately and hold position (command 0x89)."""
        self._serial.write(b"\x89")

    def _rotate(self, rotations: float, speed_rps: float, direction: int) -> None:
        """Rotate the screw by `rotations` rev at `speed_rps` rev/s in `direction` (+1 = forward, -1 = reverse)."""
        if rotations < self._MIN_ROTATIONS:
            raise ValueError(f"rotations {rotations} is below minimum {self._MIN_ROTATIONS} rev (= MIN_VOLUME_ML {self.MIN_VOLUME_ML} mL)")
        if not (self._MIN_SPEED_RPS <= speed_rps <= self.MAX_SPEED_RPS):
            raise ValueError(f"speed_rps {speed_rps} is out of range [{self._MIN_SPEED_RPS:.4f}, {self.MAX_SPEED_RPS}] (= [{self.MIN_SPEED_ML_PER_MIN}, {self.MAX_SPEED_ML_PER_MIN}] mL/min)")
        self._exit_safe_start()
        self._set_target_velocity(direction * self._rps_to_tic_velocity(speed_rps))
        time.sleep(rotations / speed_rps)
        self._halt_and_hold()

    def _continuous_rotate_worker(self, speed_rps: float, direction: int) -> None:
        """Worker thread: rotate continuously until _stop_event is set."""
        self._exit_safe_start()
        self._set_target_velocity(direction * self._rps_to_tic_velocity(speed_rps))
        self._stop_event.wait()
        self._halt_and_hold()

    def start_rotation(self, speed_rps: float, direction: int) -> None:
        """Start continuous rotation at `speed_rps` rev/s in `direction` (+1 = forward, -1 = reverse).

        Returns immediately; call stop_rotation() to stop.
        Raises RuntimeError if already rotating.
        """
        if not (self._MIN_SPEED_RPS <= speed_rps <= self.MAX_SPEED_RPS):
            raise ValueError(f"speed_rps {speed_rps} is out of range [{self._MIN_SPEED_RPS:.4f}, {self.MAX_SPEED_RPS}] (= [{self.MIN_SPEED_ML_PER_MIN}, {self.MAX_SPEED_ML_PER_MIN}] mL/min)")
        with self._lock:
            if hasattr(self, "_rotation_thread") and self._rotation_thread.is_alive():
                raise RuntimeError("Already rotating. Call stop_rotation() first.")
            self._stop_event = threading.Event()
            self._rotation_thread = threading.Thread(
                target=self._continuous_rotate_worker,
                args=(speed_rps, direction),
                daemon=True,
            )
            self._rotation_thread.start()

    def stop_rotation(self) -> None:
        """Stop continuous rotation started by start_rotation() and wait for the motor to halt."""
        self._stop_event.set()
        self._rotation_thread.join()

    def dispense(self, volume_ml: float, speed_ml_per_min: float) -> None:
        """Rotate forward to dispense `volume_ml` mL at `speed_ml_per_min` mL/min."""
        rotations = volume_ml / self._ML_PER_REV
        speed_rps = (speed_ml_per_min / 60.0) / self._ML_PER_REV
        with self._lock:
            self._rotate(rotations, speed_rps, +1)

    def suck_back(self, volume_ml: float, speed_ml_per_min: float, delay_s: float = 0.0) -> None:
        """Rotate backward to suck back `volume_ml` mL at `speed_ml_per_min` mL/min to prevent dripping.

        Args:
            delay_s: Seconds to wait after the preceding dispense before starting backward rotation.
        """
        if delay_s > 0.0:
            time.sleep(delay_s)
        rotations = volume_ml / self._ML_PER_REV
        speed_rps = (speed_ml_per_min / 60.0) / self._ML_PER_REV
        with self._lock:
            self._rotate(rotations, speed_rps, -1)

    def purge(self, volume_ml: float) -> None:
        """Rotate forward to purge `volume_ml` mL at the fixed purge speed to prime or clear the nozzle."""
        if self._purge_speed_rps is None:
            raise ValueError("purge_speed_rps is not set. Set it in devices.settings.yaml before calling purge().")
        rotations = volume_ml / self._ML_PER_REV
        with self._lock:
            self._rotate(rotations, self._purge_speed_rps, +1)

    def check_status(self) -> None:
        """No-op placeholder; serial stepper has no lightweight status query. Skipped if busy."""

    def close(self) -> None:
        """Stop the motor gracefully and close the serial connection."""
        if self._serial.is_open:
            self._halt_and_hold()
            self._enter_safe_start()
            self._deenergize()
            self._serial.close()
            self.status = "disconnected"
            self._logger.info("HighViscosityDispenser: disconnected")
