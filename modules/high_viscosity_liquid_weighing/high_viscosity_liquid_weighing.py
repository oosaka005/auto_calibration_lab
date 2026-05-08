"""High viscosity liquid weighing node.

Combines a Pololu Tic T500 stepper motor controller (driving a syringe
mechanism) with a serial analytical balance to perform gravimetric
dispensing of high-viscosity liquids.
"""

import logging
import time
from inspect import Parameter, signature

import requests
from pathlib import Path
from typing import Annotated, Any, ClassVar, Optional

import yaml
from madsci.common.types.action_types import ActionFailed, ActionSucceeded
from madsci.common.types.base_types import Error
from madsci.common.types.datapoint_types import ValueDataPoint
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
        if self.balance is not None and self.high_viscosity_dispenser is not None:
            for name in self.config.DEVICE_CLASSES:
                device = getattr(self, name)
                if device is not None:
                    device.check_status()
            self.node_state = {
                "balance_status": self.balance.status,
                "balance_last_weight_g": self.balance.current_mass_g,
                "dispenser_status": self.high_viscosity_dispenser.status,
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
    def calibrate_dispenser(
        self,
        material_name: str,
        pressure_mpa: float,
        volume_per_step_ml: float,
        speed_start_ml_per_min: float,
        speed_end_ml_per_min: float,
        speed_step_ml_per_min: float,
        suck_back_volume_ml: float,
        suck_back_speed_ml_per_min: float,
    ) -> ActionSucceeded:
        """Measure g/rev at increasing speeds to characterize dispenser performance.

        For each speed step, tares the balance, dispenses a fixed volume,
        reads the resulting mass, and calculates grams per revolution and density.
        Density [g/cm³] = mass_g / volume_per_step_ml.
        """
        try:
            self.resource_client.query_resource(resource_name=material_name)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return ActionFailed(
                    errors=[ValueError(f"Material '{material_name}' not found in Resource Manager")]
                )
            return ActionFailed(errors=[e])
        except Exception as e:
            return ActionFailed(errors=[e])

        ml_per_rev = self.high_viscosity_dispenser._ML_PER_REV
        results = []
        speed_ml_per_min = speed_start_ml_per_min
        try:
            while speed_ml_per_min <= speed_end_ml_per_min + 1e-9:
                self.balance.tare()

                while self.node_status.paused:
                    time.sleep(0.1)
                self.high_viscosity_dispenser.dispense(volume_per_step_ml, speed_ml_per_min)
                self.high_viscosity_dispenser.suck_back(suck_back_volume_ml, suck_back_speed_ml_per_min)

                mass_g = self.balance.read_weight()

                g_per_rev = mass_g / (volume_per_step_ml / ml_per_rev)
                density_g_per_cm3 = mass_g / volume_per_step_ml
                results.append({
                    "material_name": material_name,
                    "pressure_mpa": pressure_mpa,
                    "speed_ml_per_min": round(speed_ml_per_min, 4),
                    "volume_per_step_ml": volume_per_step_ml,
                    "mass_g": mass_g,
                    "g_per_rev": g_per_rev,
                    "density_g_per_cm3": density_g_per_cm3,
                })
                speed_ml_per_min += speed_step_ml_per_min

            self.data_client.submit_datapoint(
                ValueDataPoint(label="calibration_results", value=results)
            )

            baseline_g_per_rev = results[0]["g_per_rev"]
            # TODO: 安定範囲の閾値（現在10%）は実測値を確認後に見直す
            stable_results = [
                r for r in results
                if r["g_per_rev"] >= baseline_g_per_rev * 0.90
            ]
            optimal = max(stable_results, key=lambda r: r["speed_ml_per_min"])

            return ActionSucceeded(json_result={
                "calibration_results": results,
                "optimal": {
                    "material_name": material_name,
                    "pressure_mpa": pressure_mpa,
                    "speed_ml_per_min": optimal["speed_ml_per_min"],
                    "g_per_rev": optimal["g_per_rev"],
                },
            })
        except Exception as e:
            return ActionFailed(errors=[e])

    @action
    def try_suck_back(
        self,
        material_name: str,
        pressure_mpa: float,
        dispense_volume_ml: float,
        dispense_speed_ml_per_min: float,
        suck_back_delay_s: float,
        suck_back_volume_ml: float,
        suck_back_speed_ml_per_min: float,
    ) -> ActionSucceeded:
        """Dispense then suck back once for manual suck-back parameter tuning.

        Intended for interactive use from a notebook. Run repeatedly with different
        suck_back_delay_s / suck_back_volume_ml / suck_back_speed_ml_per_min values
        while visually inspecting drip and stringing behaviour. Record the best
        parameters in the Resource Manager once satisfied.

        Constraints:
            suck_back_volume_ml       : 0.004 mL <= value <= dispense_volume_ml
            suck_back_speed_ml_per_min: 0.5 <= value <= 6.0
        """
        try:
            self.resource_client.query_resource(resource_name=material_name)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return ActionFailed(
                    errors=[ValueError(f"Material '{material_name}' not found in Resource Manager")]
                )
            return ActionFailed(errors=[e])
        except Exception as e:
            return ActionFailed(errors=[e])

        if suck_back_volume_ml > dispense_volume_ml:
            return ActionFailed(errors=[ValueError(
                f"suck_back_volume_ml {suck_back_volume_ml} mL exceeds dispense_volume_ml {dispense_volume_ml:.4f} mL"
            )])

        try:
            self.high_viscosity_dispenser.dispense(dispense_volume_ml, dispense_speed_ml_per_min)
            self.high_viscosity_dispenser.suck_back(suck_back_volume_ml, suck_back_speed_ml_per_min, delay_s=suck_back_delay_s)
            return ActionSucceeded(json_result={
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
                "dispense_volume_ml": dispense_volume_ml,
                "dispense_speed_ml_per_min": dispense_speed_ml_per_min,
                "suck_back_delay_s": suck_back_delay_s,
                "suck_back_volume_ml": suck_back_volume_ml,
                "suck_back_speed_ml_per_min": suck_back_speed_ml_per_min,
            })
        except Exception as e:
            return ActionFailed(errors=[e])


if __name__ == "__main__":
    node = HighViscosityLiquidWeighingNode()
    node.start_node()
