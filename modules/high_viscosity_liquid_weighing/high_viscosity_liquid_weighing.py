"""High viscosity liquid weighing node.

Combines a Pololu Tic T500 stepper motor controller (driving a syringe
mechanism) with a serial analytical balance to perform gravimetric
dispensing of high-viscosity liquids.
"""

import logging
import time
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Any, ClassVar, Optional

import yaml
from madsci.common.types.action_types import ActionFailed, ActionSucceeded
from madsci.common.types.base_types import Error
from madsci.common.types.node_types import RestNodeConfig
from madsci.node_module.helpers import action
from madsci.node_module.rest_node_module import RestNode
from pydantic import BaseModel, create_model

from devices import DEVICE_REGISTRY


class HighViscosityLiquidWeighingConfig(
    RestNodeConfig,
    yaml_file=(
        "settings.yaml",
        "node.settings.yaml",
        "devices.settings.yaml",  # read from devices/ via _extra_search_dirs
    ),
):
    """Configuration for the high viscosity liquid weighing node.

    Reads device settings from devices/devices.settings.yaml (shared across nodes)
    and node-specific settings from node.settings.yaml.
    """

    _extra_search_dirs: ClassVar[tuple[str, ...]] = ("devices",)

    def _build_device_classes() -> dict[str, type]:
        node_cfg = yaml.safe_load(
            (Path(__file__).parent / "node.settings.yaml").read_text()
        )
        device_names: list[str] = node_cfg.get("devices", [])
        global_type: str = node_cfg.get("interface_type", "real")
        devices_cfg = yaml.safe_load(
            (Path(__file__).parent.parent.parent / "devices" / "devices.settings.yaml").read_text()
        )
        result = {}
        for name in device_names:
            cfg = devices_cfg.get(name)
            if not isinstance(cfg, dict) or "_class" not in cfg:
                raise ValueError(f"Device {name!r} not found or missing '_class' in devices.settings.yaml")
            cls_name = cfg["_class"]
            effective_type = cfg.get("_interface_type") or global_type
            if effective_type == "fake":
                fake_cls_name = cls_name + "Fake"
                if fake_cls_name not in DEVICE_REGISTRY:
                    raise ValueError(f"{fake_cls_name!r} is not registered in devices.DEVICE_REGISTRY")
                result[name] = DEVICE_REGISTRY[fake_cls_name]
            else:
                if cls_name not in DEVICE_REGISTRY:
                    raise ValueError(f"{cls_name!r} is not registered in devices.DEVICE_REGISTRY")
                result[name] = DEVICE_REGISTRY[cls_name]
        return result

    DEVICE_CLASSES: ClassVar[dict] = _build_device_classes()
    del _build_device_classes

    # Auto-generate Pydantic config models and field annotations from DEVICE_CLASSES.
    # Excludes 'self' and 'logger' (runtime-injected, not read from config files).
    # To add a device: add one entry to DEVICE_CLASSES above — nothing else needed.
    def _config_from_class(cls: type) -> type[BaseModel]:
        fields: dict = {}
        for name, param in signature(cls.__init__).parameters.items():
            if name in ("self", "logger"):
                continue
            annotation = param.annotation
            if param.default is Parameter.empty:
                fields[name] = (annotation, ...)
            else:
                fields[name] = (annotation, param.default)
        return create_model(f"{cls.__name__}Config", **fields)

    # --- Device settings (populated from devices/devices.settings.yaml) ---
    for _name, _cls in DEVICE_CLASSES.items():
        __annotations__[_name] = _config_from_class(_cls)
    del _config_from_class, _name, _cls

    # --- Node-specific operation parameters (add here when needed) ---


class HighViscosityLiquidWeighingNode(RestNode):
    """MADSci node for gravimetric high-viscosity liquid weighing.

    Combines a Pololu Tic T500 stepper controller (driving a syringe) with
    a serial analytical balance. The motor advances until the balance reports
    that the target mass has been reached.
    """

    config: HighViscosityLiquidWeighingConfig = HighViscosityLiquidWeighingConfig()
    config_model = HighViscosityLiquidWeighingConfig

    for _name, _cls in HighViscosityLiquidWeighingConfig.DEVICE_CLASSES.items():
        __annotations__[_name] = Optional[_cls]
        vars()[_name] = None
    del _name, _cls

    def startup_handler(self) -> None:
        """Open device connections and prepare the motor."""
        for name, cls in self.config.DEVICE_CLASSES.items():
            device = cls(
                **getattr(self.config, name).model_dump(),
                logger=logging.getLogger(name),
            )
            setattr(self, name, device)
        self.logger.log("HighViscosityLiquidWeighingNode: startup complete")

    def shutdown_handler(self) -> None:
        """Close device connections."""
        for name in self.config.DEVICE_CLASSES:
            getattr(self, name).close()
        self.logger.log("HighViscosityLiquidWeighingNode: shutdown complete")

    def state_handler(self) -> dict[str, Any]:
        """Report current device readings.

        Called automatically every ~2 seconds (state_update_interval).
        Set self.node_state to a dict of current physical values read from devices.
        Examples:
          - Motor: current position, error flags
          - Balance: current weight reading
          - Temperature controller: current temperature, setpoint
        Only include values that need to be monitored in real time.
        Historical data should be saved via the Data Manager instead.

        --- node_state vs node_status ---
        node_state  (this function)
          Physical values polled from devices (e.g. weight, position).
          Used for real-time dashboard display. Always overwritten, not stored historically.
          To retain historical data, save explicitly via the Data Manager.

        node_status  (managed automatically by MADSci, no need to set manually)
          Operational state of the node itself.
          - busy   : set automatically while an action is running
          - ready  : computed from busy/locked/errored etc.
          - locked : prevents any new actions from being accepted
          - paused : stops before the next device command (requires _checkpoint in actions)
          - errored: set automatically when an unhandled error occurs
        """
        if self.balance is not None and self.dispenser is not None:
            for name in self.config.DEVICE_CLASSES:
                device = getattr(self, name)
                if device is not None:
                    device.check_status()
            self.node_state = {
                "balance_status": self.balance.status,
                "balance_last_weight_g": self.balance.current_mass_g,
                "dispenser_status": self.dispenser.status,
            }

    # -----------------------------------------------------------------------
    # Actions
    #
    # Note: pause / cancel support
    #   The minimum interruptable unit is a single device command.
    #   A running command always completes; interruption happens before the next one.
    #   To support pause/cancel, call self._checkpoint() between device commands
    #   inside the action loop. See liquidhandler.py for a reference implementation.
    # -----------------------------------------------------------------------

    @action
    def tare(self) -> None:
        """Tare the balance."""
        self.balance.tare()


if __name__ == "__main__":
    node = HighViscosityLiquidWeighingNode()
    node.start_node()
