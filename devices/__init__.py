# Fake interfaces have no external dependencies and are always available.
from .balance_proprietary_fake import BalanceProprietaryFake
from .balance_sila_fake import BalanceSilaFake
from .high_viscosity_dispenser_proprietary_fake import HighViscosityDispenserProprietaryFake

# Real interfaces require optional hardware libraries (pyserial, sila2).
# They are imported conditionally so the node can start without them when
# running in fake mode (interface_type: fake in node.settings.yaml).
try:
    from .balance_proprietary import BalanceProprietary
except ImportError:
    BalanceProprietary = None  # type: ignore[assignment,misc]

try:
    from .balance_sila import BalanceSila
except ImportError:
    BalanceSila = None  # type: ignore[assignment,misc]

try:
    from .high_viscosity_dispenser_proprietary import HighViscosityDispenserProprietary
except ImportError:
    HighViscosityDispenserProprietary = None  # type: ignore[assignment,misc]

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
}

# Register real interfaces only when their libraries are available.
if BalanceProprietary is not None:
    DEVICE_REGISTRY["BalanceProprietary"] = BalanceProprietary
if BalanceSila is not None:
    DEVICE_REGISTRY["BalanceSila"] = BalanceSila
if HighViscosityDispenserProprietary is not None:
    DEVICE_REGISTRY["HighViscosityDispenserProprietary"] = HighViscosityDispenserProprietary

__all__ = [
    "BalanceProprietary",
    "BalanceProprietaryFake",
    "BalanceSila",
    "BalanceSilaFake",
    "HighViscosityDispenserProprietary",
    "HighViscosityDispenserProprietaryFake",
    "DEVICE_REGISTRY",
]
