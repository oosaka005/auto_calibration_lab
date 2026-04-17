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
                fake_cls_name = cls_name.replace("Interface", "FakeInterface")
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
        # Example of how to build node_state:
        # state: dict[str, Any] = {}
        # state["motor_position_steps"] = self.tic.get_current_position()
        # state["current_weight_g"] = self.balance.read_weight()
        # self.node_state = state
        self.node_state = {}

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

    @action
    def calibrate_density(
        self,
        rotations_per_increment: Annotated[float, "Motor rotations dispensed per increment"],
        num_increments: Annotated[int, "Number of increments to dispense"] = 5,
        speed_rps: Annotated[float, "Motor speed during calibration [rev/s]"] = 1.0,
    ) -> ActionSucceeded:
        """Estimate density [g/mL] by dispensing fixed rotation increments and measuring weight.

        Tares the balance, then dispenses rotations_per_increment num_increments times
        at speed_rps, recording cumulative weight after each increment.
        Fits density via least squares using the fixed displacement of 0.05 mL/rev.
        Returns density [g/mL], cumulative weights, and total volume dispensed.
        """
        if speed_rps > self.high_viscosity_dispenser.MAX_SPEED_RPS:
            return ActionFailed(
                errors=[Error(message=f"speed_rps {speed_rps} exceeds MAX_SPEED_RPS {self.high_viscosity_dispenser.MAX_SPEED_RPS}")]
            )

        self.balance.tare()
        cumulative_weights: list[float] = []

        for _ in range(num_increments):
            self.high_viscosity_dispenser.dispense(rotations_per_increment, speed_rps)
            weight = self.balance.read_weight()
            cumulative_weights.append(weight)

        total_rotations = rotations_per_increment * num_increments
        total_volume_mL = total_rotations * self.high_viscosity_dispenser._ML_PER_REV
        density = self._calc_density(cumulative_weights, rotations_per_increment)

        return ActionSucceeded(
            json_result={
                "density_g_per_mL": density,
                "total_rotations": total_rotations,
                "total_volume_mL": total_volume_mL,
                "cumulative_weights_g": cumulative_weights,
            }
        )

    @action
    def calibrate_speed(
        self,
        min_speed_rps: Annotated[float, "Minimum motor speed [rev/s]"],
        max_speed_rps: Annotated[float, "Maximum motor speed [rev/s]"],
        duration_s: Annotated[float, "Duration to run motor at each speed [s]"] = 10.0,
    ) -> ActionSucceeded:
        """Measure dispensing rate [g/min] at minimum and maximum motor speeds.

        Tares the balance, runs motor at min_speed_rps for duration_s seconds,
        reads weight to compute rate. Repeats at max_speed_rps.
        Returns dispensing rate [g/min] at each speed.
        """
        if max_speed_rps > self.high_viscosity_dispenser.MAX_SPEED_RPS:
            return ActionFailed(
                errors=[Error(message=f"max_speed_rps {max_speed_rps} exceeds MAX_SPEED_RPS {self.high_viscosity_dispenser.MAX_SPEED_RPS}")]
            )

        self.balance.tare()
        self.high_viscosity_dispenser.dispense(min_speed_rps * duration_s, min_speed_rps)
        weight_at_min = self.balance.read_weight()
        rate_min_g_per_min = weight_at_min / duration_s * 60.0

        self.balance.tare()
        self.high_viscosity_dispenser.dispense(max_speed_rps * duration_s, max_speed_rps)
        weight_at_max = self.balance.read_weight()
        rate_max_g_per_min = weight_at_max / duration_s * 60.0

        return ActionSucceeded(
            json_result={
                "min_speed_rps": min_speed_rps,
                "rate_at_min_speed_g_per_min": rate_min_g_per_min,
                "max_speed_rps": max_speed_rps,
                "rate_at_max_speed_g_per_min": rate_max_g_per_min,
                "duration_s": duration_s,
            }
        )

    def _calc_density(
        self,
        cumulative_weights: list[float],
        rotations_per_increment: float,
    ) -> float:
        """Estimate density [g/mL] from cumulative weight measurements via least squares.

        Fits weight_i = density × volume_i where volume_i = (i+1) * rotations_per_increment * ML_PER_REV.
        """
        ml_per_rev = self.high_viscosity_dispenser._ML_PER_REV
        volumes = [
            (i + 1) * rotations_per_increment * ml_per_rev
            for i in range(len(cumulative_weights))
        ]
        numerator = sum(v * w for v, w in zip(volumes, cumulative_weights))
        denominator = sum(v ** 2 for v in volumes)
        return numerator / denominator


if __name__ == "__main__":
    node = HighViscosityLiquidWeighingNode()
    node.start_node()
