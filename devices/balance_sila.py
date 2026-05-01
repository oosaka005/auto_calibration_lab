"""SiLA2 client interface for an analytical balance."""

import logging
from typing import Optional

from sila2.client import SilaClient


class BalanceSila:
    """SiLA2 client interface for an analytical balance.

    Connects to a balance_sila_server running on a remote host (e.g. Raspberry Pi via TailScale).
    Provides the same public API as BalanceProprietary.
    """

    def __init__(
        self,
        host: str,
        sila_port: int = 50052,
        insecure: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self.status = "disconnected"
        self.current_mass_g: float = 0.0
        self._client = SilaClient(address=host, port=sila_port, insecure=insecure)
        self.status = "connected"
        self._logger.info(f"BalanceSila: connected to {host}:{sila_port}")

    def read_weight(self, settle_time: float = 2.0) -> float:
        """Send a read command to the balance and return the measured weight in grams."""
        try:
            response = self._client.Balance.ReadWeight()
        except Exception:
            self.status = "disconnected"
            raise
        self.current_mass_g = response.Weight
        return self.current_mass_g

    def tare(self) -> None:
        """Send tare command to the balance."""
        try:
            self._client.Balance.Tare()
        except Exception:
            self.status = "disconnected"
            raise
        self.current_mass_g = 0.0

    def zero(self) -> None:
        """Send zero command to the balance."""
        try:
            self._client.Balance.Zero()
        except Exception:
            self.status = "disconnected"
            raise
        self.current_mass_g = 0.0

    def close(self) -> None:
        """Close the SiLA client connection."""
        self._client.close()
        self.status = "disconnected"
        self._logger.info("BalanceSila: disconnected")

    def check_status(self) -> None:
        """Read Status property from SiLA server to verify connection. Updates status on failure."""
        try:
            self.status = self._client.Balance.Status.get()
        except Exception:
            self.status = "disconnected"
