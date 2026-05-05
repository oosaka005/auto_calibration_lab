"""Fake interface for the high viscosity dispenser (testing without hardware)."""

import logging
import random
import time
from typing import Optional


class HighViscosityDispenserProprietaryFake:
    """Simulated interface for the Pololu Tic T500 stepper motor controller.

    Provides the same API as HighViscosityDispenserProprietary but simulates
    motor motion instead of communicating with hardware.
    """

    MAX_SPEED_RPS: float = 2.0                                             # eco-PEN450 hardware limit: 120 RPM (internal use)
    MAX_SPEED_ML_PER_MIN: float = 6.0                                      # eco-PEN450 hardware limit: 6.0 mL/min
    MIN_SPEED_ML_PER_MIN: float = 0.5                                      # eco-PEN450 minimum stable speed
    MIN_VOLUME_ML: float = 0.004                                           # eco-PEN450 minimum meaningful movement volume
    _ML_PER_REV: float = 0.05                                              # eco-PEN450 fixed displacement: 0.05 mL/rev
    _MIN_ROTATIONS: float = MIN_VOLUME_ML / _ML_PER_REV                    # = 0.08 rev (internal use)
    _MIN_SPEED_RPS: float = (MIN_SPEED_ML_PER_MIN / 60.0) / _ML_PER_REV   # ≈ 0.167 rps (internal use)

    def __init__(
        self,
        port: str = "FAKE",
        full_steps_per_rev: int = 200,
        microstep_multiplier: int = 1,
        purge_speed_rps: float = 0.5,
        baud_rate: int = 9600,
        latency: float = 0.1,
        failure_rate: float = 0.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        if purge_speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"purge_speed_rps {purge_speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
        self._full_steps_per_rev = full_steps_per_rev
        self._microstep_multiplier = microstep_multiplier
        self._purge_speed_rps = purge_speed_rps
        self._latency = latency
        self._failure_rate = failure_rate
        self.status = "connected"
        self._logger.info(f"HighViscosityDispenserProprietaryFake: connected (fake, port={port})")

    def _maybe_fail(self) -> None:
        """Randomly raise an exception based on failure_rate."""
        if random.random() < self._failure_rate:
            raise Exception("Simulated failure: dispenser error")

    def _rotate(self, rotations: float, speed_rps: float, direction: int) -> None:
        """Simulate rotation by `rotations` rev at `speed_rps` rev/s in `direction` (+1 = forward, -1 = reverse)."""
        if rotations < self._MIN_ROTATIONS:
            raise ValueError(f"rotations {rotations} is below minimum {self._MIN_ROTATIONS} rev (= MIN_VOLUME_ML {self.MIN_VOLUME_ML} mL)")
        if not (self._MIN_SPEED_RPS <= speed_rps <= self.MAX_SPEED_RPS):
            raise ValueError(f"speed_rps {speed_rps} is out of range [{self._MIN_SPEED_RPS:.4f}, {self.MAX_SPEED_RPS}] (= [{self.MIN_SPEED_ML_PER_MIN}, {self.MAX_SPEED_ML_PER_MIN}] mL/min)")
        self._maybe_fail()
        time.sleep((rotations / speed_rps) * self._latency)

    def dispense(self, volume_ml: float, speed_ml_per_min: float) -> None:
        """Simulate forward rotation to dispense `volume_ml` mL at `speed_ml_per_min` mL/min."""
        rotations = volume_ml / self._ML_PER_REV
        speed_rps = (speed_ml_per_min / 60.0) / self._ML_PER_REV
        self._rotate(rotations, speed_rps, +1)

    def suck_back(self, volume_ml: float, speed_ml_per_min: float) -> None:
        """Simulate backward rotation to suck back `volume_ml` mL at `speed_ml_per_min` mL/min."""
        rotations = volume_ml / self._ML_PER_REV
        speed_rps = (speed_ml_per_min / 60.0) / self._ML_PER_REV
        self._rotate(rotations, speed_rps, -1)

    def purge(self, volume_ml: float) -> None:
        """Simulate purge rotation to dispense `volume_ml` mL at the fixed purge speed."""
        rotations = volume_ml / self._ML_PER_REV
        self._rotate(rotations, self._purge_speed_rps, +1)

    def close(self) -> None:
        """Simulate disconnection."""
        self.status = "disconnected"
        self._logger.info("HighViscosityDispenserProprietaryFake: disconnected")

    def check_status(self) -> None:
        """No-op for fake interface; status is always connected."""
