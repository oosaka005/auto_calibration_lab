"""Serial interface for the Pololu Tic T500 stepper motor controller.

Reference: https://www.pololu.com/docs/0J71
Serial command protocol is used (not native USB).

--- Wiring (Raspberry Pi 5) ---

    GPIO14 (pin 8,  TX) --> Tic RX
    GPIO15 (pin 10, RX) <-- Tic TX
    GND    (pin 6)      --> Tic GND
    port = "/dev/serial0"
    Enable the serial port via raspi-config:
        Interface Options -> Serial Port -> login shell: No, hardware enabled: Yes

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

    MAX_SPEED_RPS: float = 2.0   # eco-PEN450 hardware limit: 120 RPM
    _ML_PER_REV: float = 0.05    # eco-PEN450 fixed displacement: 0.05 mL/rev

    def __init__(
        self,
        port: str,
        full_steps_per_rev: int,
        microstep_multiplier: int,
        purge_speed_rps: float,
        baud_rate: int = 9600,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        if purge_speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"purge_speed_rps {purge_speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
        self._lock = threading.Lock()
        self._full_steps_per_rev = full_steps_per_rev
        self._microstep_multiplier = microstep_multiplier
        self._purge_speed_rps = purge_speed_rps
        self._serial = serial.Serial(port, baud_rate, timeout=1.0)
        # Reset → reload EEPROM settings, then bring up to operable state.
        self._serial.write(b"\xb0")  # Reset (0xB0)
        time.sleep(0.01)             # Wait ≥10 ms for reset to complete
        self._energize()
        self._exit_safe_start()
        self.status = "connected"
        self._logger.info(f"HighViscosityDispenser: connected on {port}")

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
        if speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"speed_rps {speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
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
        if speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"speed_rps {speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
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

    def dispense(self, rotations: float, speed_rps: float) -> None:
        """Rotate forward by `rotations` rev at `speed_rps` rev/s to dispense material."""
        with self._lock:
            self._rotate(rotations, speed_rps, +1)

    def suck_back(self, rotations: float, speed_rps: float) -> None:
        """Rotate backward by `rotations` rev at `speed_rps` rev/s to prevent dripping."""
        with self._lock:
            self._rotate(rotations, speed_rps, -1)

    def purge(self, rotations: float) -> None:
        """Rotate forward by `rotations` rev at the fixed purge speed to prime or clear the nozzle."""
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
