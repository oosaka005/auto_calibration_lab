"""Serial interface for the Pololu Tic T500 stepper motor controller.

Reference: https://www.pololu.com/docs/0J71
Serial command protocol is used (not native USB).
"""

import logging
import time
from typing import Optional

import serial


class HighViscosityDispenserInterface:
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
        self.motion_status = "idle"
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
        """Set target velocity in 0.0001 microsteps/s (command 0xE5, 32-bit LE signed)."""
        self._serial.write(b"\xe5" + velocity.to_bytes(4, byteorder="little", signed=True))

    def _rps_to_tic_velocity(self, speed_rps: float) -> int:
        """Convert rev/s to Tic T500 velocity units (0.0001 microsteps/s)."""
        return int(speed_rps * self._full_steps_per_rev * self._microstep_multiplier * 10000)

    def _halt_and_hold(self) -> None:
        """Stop motion immediately and hold position (command 0x89)."""
        self._serial.write(b"\x89")

    def dispense(self, rotations: float, speed_rps: float) -> None:
        """Rotate forward by `rotations` rev at `speed_rps` rev/s to dispense material."""
        if speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"speed_rps {speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
        self.motion_status = "dispensing"
        self._exit_safe_start()
        self._set_target_velocity(self._rps_to_tic_velocity(speed_rps))
        time.sleep(rotations / speed_rps)
        self._halt_and_hold()
        self.motion_status = "idle"

    def suck_back(self, rotations: float, speed_rps: float) -> None:
        """Rotate backward by `rotations` rev at `speed_rps` rev/s to prevent dripping."""
        self.motion_status = "purging"
        self._exit_safe_start()
        self._set_target_velocity(-self._rps_to_tic_velocity(speed_rps))
        time.sleep(rotations / speed_rps)
        self._halt_and_hold()
        self.motion_status = "idle"

    def purge(self, rotations: float) -> None:
        """Rotate forward by `rotations` rev at the fixed purge speed to prime or clear the nozzle."""
        self.motion_status = "purging"
        self._exit_safe_start()
        self._set_target_velocity(self._rps_to_tic_velocity(self._purge_speed_rps))
        time.sleep(rotations / self._purge_speed_rps)
        self._halt_and_hold()
        self.motion_status = "idle"

    def close(self) -> None:
        """Stop the motor gracefully and close the serial connection."""
        if self._serial.is_open:
            self._halt_and_hold()
            self._enter_safe_start()
            self._deenergize()
            self._serial.close()
            self.status = "disconnected"
            self.motion_status = "idle"
            self._logger.info("HighViscosityDispenser: disconnected")
