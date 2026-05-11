# Fake interfaces have no external dependencies and are always available.
from .balance_proprietary_fake import BalanceProprietaryFake
from .balance_sila_fake import BalanceSilaFake
from .high_viscosity_dispenser_proprietary_fake import HighViscosityDispenserProprietaryFake

# Real interfaces require hardware-specific libraries (pyserial, sila2).
# These are installed in the Docker image via devices/requirements.txt (see Dockerfile).
from .balance_proprietary import BalanceProprietary
from .balance_sila import BalanceSila
from .high_viscosity_dispenser_proprietary import HighViscosityDispenserProprietary

# Maps the class name string (written in devices.settings.yaml) to the class itself.
# Add a new entry here when adding a new device class.
#
# Naming convention:
#   Real interfaces:  {DeviceName}{Protocol}          e.g. BalanceProprietary, BalanceSila
#   Fake interfaces:  {DeviceName}{Protocol}Fake      e.g. BalanceProprietaryFake, BalanceSilaFake
#   The fake class name is derived by appending "Fake" to the real class name.
DEVICE_REGISTRY: dict[str, type] = {
    "BalanceProprietaryFake": BalanceProprietaryFake,
    "BalanceSilaFake": BalanceSilaFake,
    "HighViscosityDispenserProprietaryFake": HighViscosityDispenserProprietaryFake,
    "BalanceProprietary": BalanceProprietary,
    "BalanceSila": BalanceSila,
    "HighViscosityDispenserProprietary": HighViscosityDispenserProprietary,
}

__all__ = [
    "BalanceProprietary",
    "BalanceProprietaryFake",
    "BalanceSila",
    "BalanceSilaFake",
    "HighViscosityDispenserProprietary",
    "HighViscosityDispenserProprietaryFake",
    "DEVICE_REGISTRY",
]
