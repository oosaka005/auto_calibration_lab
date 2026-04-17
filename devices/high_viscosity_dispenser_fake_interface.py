"""Fake interface for the high viscosity dispenser (testing without hardware)."""

import logging
import random
import time
from typing import Optional


class HighViscosityDispenserFakeInterface:
    """Simulated interface for the Pololu Tic T500 stepper motor controller.

    Provides the same API as HighViscosityDispenserInterface but simulates
    motor motion instead of communicating with hardware.
    """

    MAX_SPEED_RPS: float = 2.0   # eco-PEN450 hardware limit: 120 RPM
    _ML_PER_REV: float = 0.05    # eco-PEN450 fixed displacement: 0.05 mL/rev

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
        self.motion_status = "idle"
        self._logger.info(f"HighViscosityDispenserFakeInterface: connected (fake, port={port})")

    def _maybe_fail(self) -> None:
        """Randomly raise an exception based on failure_rate."""
        if random.random() < self._failure_rate:
            raise Exception("Simulated failure: dispenser error")

    def dispense(self, rotations: float, speed_rps: float) -> None:
        """Simulate forward rotation by `rotations` rev at `speed_rps` rev/s."""
        if speed_rps > self.MAX_SPEED_RPS:
            raise ValueError(f"speed_rps {speed_rps} exceeds MAX_SPEED_RPS {self.MAX_SPEED_RPS}")
        self._maybe_fail()
        self.motion_status = "dispensing"
        time.sleep((rotations / speed_rps) * self._latency)
        self.motion_status = "idle"

    def suck_back(self, rotations: float, speed_rps: float) -> None:
        """Simulate backward rotation by `rotations` rev at `speed_rps` rev/s."""
        self._maybe_fail()
        self.motion_status = "purging"
        time.sleep((rotations / speed_rps) * self._latency)
        self.motion_status = "idle"

    def purge(self, rotations: float) -> None:
        """Simulate purge rotation by `rotations` rev at the fixed purge speed."""
        self._maybe_fail()
        self.motion_status = "purging"
        time.sleep((rotations / self._purge_speed_rps) * self._latency)
        self.motion_status = "idle"

    def close(self) -> None:
        """Simulate disconnection."""
        self.status = "disconnected"
        self.motion_status = "idle"
        self._logger.info("HighViscosityDispenserFakeInterface: disconnected")
