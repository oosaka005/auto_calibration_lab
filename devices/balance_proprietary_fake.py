"""Fake interface for an analytical balance (testing without hardware)."""

import logging
import random
import time
from typing import Optional


class BalanceProprietaryFake:
    """Simulated interface for an analytical balance.

    Provides the same API as BalanceProprietary but generates fake data
    instead of communicating with hardware.
    """

    def __init__(
        self,
        port: str = "FAKE",
        baud_rate: int = 9600,
        timeout: float = 1.0,
        latency: float = 0.1,
        base_mass_g: float = 0.0,
        noise_std: float = 0.01,
        failure_rate: float = 0.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._latency = latency
        self._base_mass_g = base_mass_g
        self._noise_std = noise_std
        self._failure_rate = failure_rate
        self.status = "connected"
        self.current_mass_g: float = base_mass_g
        self._logger.info(f"BalanceProprietaryFake: connected (fake, port={port})")

    def _maybe_fail(self) -> None:
        """Randomly raise an exception based on failure_rate."""
        if random.random() < self._failure_rate:
            raise Exception("Simulated failure: balance error")

    def read_weight(self, settle_time: float = 2.0) -> float:
        """Read weight after optional settling delay. Returns value in grams."""
        self._maybe_fail()
        if settle_time > 0:
            time.sleep(settle_time * self._latency)
        value = self.current_mass_g + random.gauss(0, self._noise_std)
        self.current_mass_g = round(value, 4)
        return self.current_mass_g

    def tare(self) -> None:
        """Simulate tare command."""
        self._maybe_fail()
        time.sleep(1.0 * self._latency)
        self._base_mass_g = 0.0
        self.current_mass_g = 0.0

    def zero(self) -> None:
        """Simulate zero command."""
        self._maybe_fail()
        time.sleep(1.0 * self._latency)
        self._base_mass_g = 0.0
        self.current_mass_g = 0.0

    def close(self) -> None:
        """Simulate disconnection."""
        self.status = "disconnected"
        self._logger.info("BalanceProprietaryFake: disconnected")
