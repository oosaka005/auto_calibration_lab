from .balance_interface import BalanceInterface
from .balance_fake_interface import BalanceFakeInterface
from .high_viscosity_dispenser_interface import HighViscosityDispenserInterface
from .high_viscosity_dispenser_fake_interface import HighViscosityDispenserFakeInterface

# Maps the class name string (written in devices.settings.yaml) to the class itself.
# Add a new entry here when adding a new device class.
DEVICE_REGISTRY: dict[str, type] = {
    "BalanceInterface": BalanceInterface,
    "BalanceFakeInterface": BalanceFakeInterface,
    "HighViscosityDispenserInterface": HighViscosityDispenserInterface,
    "HighViscosityDispenserFakeInterface": HighViscosityDispenserFakeInterface,
}

__all__ = [
    "BalanceInterface",
    "BalanceFakeInterface",
    "HighViscosityDispenserInterface",
    "HighViscosityDispenserFakeInterface",
    "DEVICE_REGISTRY",
]
