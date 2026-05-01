from .balance_proprietary import BalanceProprietary
from .balance_proprietary_fake import BalanceProprietaryFake
from .high_viscosity_dispenser_proprietary import HighViscosityDispenserProprietary
from .high_viscosity_dispenser_proprietary_fake import HighViscosityDispenserProprietaryFake

# Maps the class name string (written in devices.settings.yaml) to the class itself.
# Add a new entry here when adding a new device class.
#
# Naming convention:
#   Real interfaces:  {DeviceName}{Protocol}          e.g. BalanceProprietary, BalanceSila
#   Fake interfaces:  {DeviceName}{Protocol}Fake      e.g. BalanceProprietaryFake, BalanceSilaFake
#   The fake class name is derived by appending "Fake" to the real class name.
DEVICE_REGISTRY: dict[str, type] = {
    "BalanceProprietary": BalanceProprietary,
    "BalanceProprietaryFake": BalanceProprietaryFake,
    "HighViscosityDispenserProprietary": HighViscosityDispenserProprietary,
    "HighViscosityDispenserProprietaryFake": HighViscosityDispenserProprietaryFake,
}

__all__ = [
    "BalanceProprietary",
    "BalanceProprietaryFake",
    "HighViscosityDispenserProprietary",
    "HighViscosityDispenserProprietaryFake",
    "DEVICE_REGISTRY",
]
