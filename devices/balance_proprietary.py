"""Serial interface for an analytical balance."""

import logging
import time
from typing import Optional

import serial


class BalanceProprietary:
    """Serial interface for an analytical balance."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 9600,
        timeout: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self.status = "disconnected"
        self.current_mass_g: float = 0.0
        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=timeout,
        )
        self.status = "connected"
        self._logger.info(f"Balance: connected on {port}")

    def _read_response(self) -> str:
        """Read characters from serial until the unit indicator 'g' is received."""
        accumulated = ""
        while True:
            char_bytes = self._serial.read(1)
            if not char_bytes:
                raise TimeoutError("Balance: no response received")
            char = char_bytes.decode()
            if char == "g":
                break
            accumulated += char
        return accumulated

    def read_weight(self, settle_time: float = 2.0) -> float:
        """Read weight after optional settling delay. Returns value in grams."""
        if settle_time > 0:
            time.sleep(settle_time)
        self._serial.write(b"R")
        raw = self._read_response()
        value = float(raw.replace("\r", "").replace("\n", "").strip())
        self.current_mass_g = value
        return value

    def tare(self) -> None:
        """Send tare command and wait for completion."""
        self._serial.write(b"T")
        time.sleep(1)
        self.current_mass_g = 0.0

    def zero(self) -> None:
        """Send zero command and wait for completion."""
        self._serial.write(b"Z")
        time.sleep(1)
        self.current_mass_g = 0.0

    def close(self) -> None:
        """Close the serial connection."""
        if self._serial.is_open:
            self._serial.close()
            self.status = "disconnected"
            self._logger.info("Balance: disconnected")
