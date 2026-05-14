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
from madsci.common.types.admin_command_types import AdminCommandResponse
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
    # Admin Commands
    #
    # MADSci auto-registers any method whose name matches an AdminCommands enum value.
    # Add all candidate commands here. Implement the body when needed; comment out
    # the entire method (including @decorator) when the command is not applicable to
    # this node.
    #
    # Provided by framework (do NOT re-implement here):
    #   lock / unlock  — prevents new actions from being accepted
    #   reset          — clears errored / stopped state
    #   shutdown       — stops the node process
    # -----------------------------------------------------------------------

    def pause(self) -> AdminCommandResponse:
        """Pause before the next device command."""
        self.node_status.paused = True
        return AdminCommandResponse()

    def resume(self) -> AdminCommandResponse:
        """Resume a paused node."""
        self.node_status.paused = False
        return AdminCommandResponse()

    # def cancel(self) -> AdminCommandResponse:
    #     """Cancel the currently running action.
    #     To implement: add a self._cancelled flag (node_status has no cancel flag),
    #     set it here, and raise CancelledError in _checkpoint().
    #     """
    #     # self._cancelled = True
    #     return AdminCommandResponse()

    # def safety_stop(self) -> AdminCommandResponse:
    #     """Emergency stop. Implement when physical safety devices (e-stop button etc.) are connected."""
    #     # self.dispenser.halt()
    #     # self.node_status.stopped = True
    #     return AdminCommandResponse()

    # def get_location(self) -> AdminCommandResponse:
    #     """Return physical coordinates of this node. Mainly used for robot arm nodes."""
    #     # return AdminCommandResponse(data=[x, y, z, rotation])
    #     return AdminCommandResponse()


    def _checkpoint(self) -> None:
        """Check node status flags between device commands.

        paused → block here until resume() clears the flag.
        """
        while self.node_status.paused:
            time.sleep(0.1)

    # -----------------------------------------------------------------------
    # Actions
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
    ) -> dict:
        """Measure g/rev at increasing speeds to characterize dispenser performance.

        For each speed step, tares the balance, dispenses a fixed volume,
        reads the resulting mass, and calculates grams per revolution and density.
        Density [g/cm³] = mass_g / volume_per_step_ml.

        Suck-back params are read from dispensing_params[high_viscosity_dispenser][suck_back]
        in the Resource Manager. Register them via material_management.ipynb before running.
        """
        try:
            material = self.resource_client.query_resource(
                resource_name=material_name,
            )
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return ActionFailed(
                    errors=[ValueError(f"Material '{material_name}' not found in Resource Manager")]
                )
            return ActionFailed(errors=[e])
        except Exception as e:
            return ActionFailed(errors=[e])

        attrs = material.attributes or {}
        device_params = attrs.get("dispensing_params", {}).get("high_viscosity_dispenser", {})
        suck_back = device_params.get("suck_back", {})
        suck_back_volume_ml = suck_back.get("volume_ml")
        suck_back_delay_s = suck_back.get("delay_s")
        if suck_back_volume_ml is None or suck_back_delay_s is None:
            return ActionFailed(
                errors=[ValueError(
                    f"Material '{material_name}' has no dispensing_params.high_viscosity_dispenser.suck_back. "
                    "Register them via material_management.ipynb before calibrating."
                )]
            )

        results = []
        n_steps = round((speed_end_ml_per_min - speed_start_ml_per_min) / speed_step_ml_per_min) + 1
        try:
            for i in range(n_steps):
                speed_ml_per_min = round(speed_start_ml_per_min + i * speed_step_ml_per_min, 4)

                self._checkpoint()

                self.balance.tare()

                self.high_viscosity_dispenser.dispense(volume_per_step_ml, speed_ml_per_min)
                self.high_viscosity_dispenser.suck_back(suck_back_volume_ml, delay_s=suck_back_delay_s)

                mass_g = self.balance.read_weight()

                density_g_per_cm3 = mass_g / volume_per_step_ml
                results.append({
                    "speed_ml_per_min": speed_ml_per_min,
                    "mass_g": mass_g,
                    "density_g_per_cm3": density_g_per_cm3,
                })

            # Throughput: point with maximum density × speed (g/min)
            throughput = max(results, key=lambda r: r["density_g_per_cm3"] * r["speed_ml_per_min"])
            # Accuracy: lowest speed point (closest to true value)
            accuracy = min(results, key=lambda r: r["speed_ml_per_min"])

            return ActionSucceeded(json_result={
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
                "device_name": "high_viscosity_dispenser",
                "volume_per_step_ml": volume_per_step_ml,
                "calibration_results": results,
                "throughput": {
                    "speed_ml_per_min": throughput["speed_ml_per_min"],
                    "density_g_per_cm3": throughput["density_g_per_cm3"],
                },
                "accuracy": {
                    "speed_ml_per_min": accuracy["speed_ml_per_min"],
                    "density_g_per_cm3": accuracy["density_g_per_cm3"],
                },
            })
        except Exception as e:
            return ActionFailed(errors=[e])

    @action
    def dispense(
        self,
        material_name: str,
        target_mass_g: float,
        pressure_mpa: float,
    ) -> dict:
        """Dispense a target mass of a high-viscosity liquid using a two-phase gravimetric strategy.

        Phase 1 (Throughput): Repeatedly dispenses 80% of the remaining mass at throughput speed
        with suck-back, until remaining mass falls within min_shot_g × 10.
        Skipped entirely if the initial remaining mass is already ≤ min_shot_g × 10.

        Phase 2 (Precision): Repeatedly dispenses 90% of the remaining mass at accuracy speed,
        waits min_shot.wait_s, reads the balance, and repeats until remaining mass ≤ min_shot_g.
        No suck-back is performed during the precision phase.

        min_shot, dispensing parameters (speed, density), and suck-back parameters are read from
        the Resource Manager (schema v1.3). Register them via material_management.ipynb and
        dispenser_check.ipynb before running.
        """
        # --- [1] Fetch material parameters from Resource Manager ---
        try:
            material = self.resource_client.query_resource(resource_name=material_name)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return ActionFailed(
                    errors=[ValueError(f"Material '{material_name}' not found in Resource Manager")]
                )
            return ActionFailed(errors=[e])
        except Exception as e:
            return ActionFailed(errors=[e])

        attrs = material.attributes or {}
        device_params = attrs.get("dispensing_params", {}).get("high_viscosity_dispenser", {})

        suck_back = device_params.get("suck_back", {})
        suck_back_volume_ml = suck_back.get("volume_ml")
        suck_back_delay_s = suck_back.get("delay_s")
        if suck_back_volume_ml is None or suck_back_delay_s is None:
            return ActionFailed(
                errors=[ValueError(
                    f"Material '{material_name}' has no dispensing_params.high_viscosity_dispenser.suck_back. "
                    "Register suck-back parameters via material_management.ipynb before dispensing."
                )]
            )

        pressure_key = f"{pressure_mpa}MPa"
        pressure_params = device_params.get(pressure_key, {})
        throughput = pressure_params.get("throughput", {})
        throughput_speed = throughput.get("speed_ml_per_min")
        throughput_density = throughput.get("density_g_per_cm3")
        accuracy = pressure_params.get("accuracy", {})
        accuracy_speed = accuracy.get("speed_ml_per_min")
        accuracy_density = accuracy.get("density_g_per_cm3")

        if throughput_speed is None or accuracy_speed is None:
            return ActionFailed(
                errors=[ValueError(
                    f"Material '{material_name}' has no dispensing_params for '{pressure_key}'. "
                    "Run calibrate_dispenser via dispenser_check.ipynb before dispensing."
                )]
            )

        nominal_density = attrs.get("physical_properties_nominal", {}).get("density_g_per_cm3")
        if throughput_density is None:
            throughput_density = nominal_density
        if throughput_density is None:
            return ActionFailed(
                errors=[ValueError(
                    f"Material '{material_name}' has no throughput density or nominal density. "
                    "Register physical_properties_nominal.density_g_per_cm3 via material_management.ipynb."
                )]
            )
        if accuracy_density is None:
            accuracy_density = throughput_density

        min_shot = pressure_params.get("min_shot", {})
        min_shot_volume_ml = min_shot.get("commanded_volume_ml")
        min_shot_wait_s = min_shot.get("wait_s")
        min_shot_mass_mg = min_shot.get("measured_mass_mg")
        if min_shot_volume_ml is None or min_shot_wait_s is None or min_shot_mass_mg is None:
            return ActionFailed(
                errors=[ValueError(
                    f"Material '{material_name}' has no min_shot data for '{pressure_key}'. "
                    "Measure min_shot manually via dispenser_check.ipynb before dispensing."
                )]
            )
        min_shot_g: float = min_shot_mass_mg / 1000.0

        # --- [2] Constants ---
        THROUGHPUT_RATIO: float = 0.80
        PRECISION_RATIO: float = 1.00
        MAX_ITERATIONS: int = 10
        throughput_threshold_g: float = min_shot_g * 10.0
        precision_threshold_g: float = min_shot_g / 2.0

        total_dispensed_volume_ml: float = 0.0
        measured_mass_g: float = 0.0
        remaining_mass_g: float = target_mass_g
        throughput_iterations: int = 0
        precision_iterations: int = 0

        try:
            # --- [3] Tare balance ---
            t_start = time.monotonic()
            self.balance.tare()

            # --- [3b] Sub-min-shot: target ≤ min_shot_g/2 → single min_shot only ---
            if target_mass_g <= precision_threshold_g:
                self.high_viscosity_dispenser.dispense(min_shot_volume_ml, accuracy_speed)
                time.sleep(min_shot_wait_s)
                total_dispensed_volume_ml = min_shot_volume_ml
                measured_mass_g = self.balance.read_weight()
                elapsed_s = time.monotonic() - t_start
                return ActionSucceeded(json_result={
                    "material_name": material_name,
                    "pressure_mpa": pressure_mpa,
                    "target_mass_g": target_mass_g,
                    "measured_mass_g": measured_mass_g,
                    "density_g_per_cm3": (
                        measured_mass_g / total_dispensed_volume_ml
                        if total_dispensed_volume_ml > 0 else None
                    ),
                    "total_dispensed_volume_ml": total_dispensed_volume_ml,
                    "throughput_iterations": 0,
                    "precision_iterations": 0,
                    "elapsed_s": round(elapsed_s, 2),
                })

            # --- [4] Throughput phase ---
            # Repeat until remaining ≤ min_shot_g × 10. Skip entirely if already below threshold.
            while remaining_mass_g > throughput_threshold_g:
                self._checkpoint()
                volume = remaining_mass_g * THROUGHPUT_RATIO / throughput_density
                self.high_viscosity_dispenser.dispense(volume, throughput_speed)
                self.high_viscosity_dispenser.suck_back(suck_back_volume_ml, delay_s=suck_back_delay_s)
                total_dispensed_volume_ml += volume - suck_back_volume_ml
                measured_mass_g = self.balance.read_weight()
                remaining_mass_g = target_mass_g - measured_mass_g
                throughput_iterations += 1
                if throughput_iterations >= MAX_ITERATIONS:
                    return ActionFailed(
                        errors=[ValueError(
                            f"Throughput phase exceeded {MAX_ITERATIONS} iterations. "
                            f"target={target_mass_g} g, measured={measured_mass_g:.4f} g"
                        )]
                    )

            # --- [5] Precision phase ---
            # Repeat until remaining ≤ min_shot_g/2.
            # If remaining < min_shot_g, use min_shot_volume_ml (device minimum) instead of
            # calculated volume, which would be below the physical dispensing minimum.
            while remaining_mass_g > precision_threshold_g:
                self._checkpoint()
                if remaining_mass_g < min_shot_g:
                    volume = min_shot_volume_ml
                else:
                    volume = remaining_mass_g * PRECISION_RATIO / accuracy_density
                self.high_viscosity_dispenser.dispense(volume, accuracy_speed)
                time.sleep(min_shot_wait_s)
                total_dispensed_volume_ml += volume
                measured_mass_g = self.balance.read_weight()
                remaining_mass_g = target_mass_g - measured_mass_g
                precision_iterations += 1
                if precision_iterations >= MAX_ITERATIONS:
                    return ActionFailed(
                        errors=[ValueError(
                            f"Precision phase exceeded {MAX_ITERATIONS} iterations. "
                            f"target={target_mass_g} g, measured={measured_mass_g:.4f} g"
                        )]
                    )

            # --- [6] Return results ---
            density_g_per_cm3 = (
                measured_mass_g / total_dispensed_volume_ml
                if total_dispensed_volume_ml > 0
                else None
            )
            elapsed_s = time.monotonic() - t_start
            return ActionSucceeded(json_result={
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
                "target_mass_g": target_mass_g,
                "measured_mass_g": measured_mass_g,
                "density_g_per_cm3": density_g_per_cm3,
                "total_dispensed_volume_ml": total_dispensed_volume_ml,
                "throughput_iterations": throughput_iterations,
                "precision_iterations": precision_iterations,
                "elapsed_s": round(elapsed_s, 2),
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
    ) -> dict:
        """Dispense then suck back once for manual suck-back parameter tuning.

        Intended for interactive use from a notebook. Run repeatedly with different
        suck_back_delay_s / suck_back_volume_ml values while visually inspecting
        drip and stringing behaviour. Record the best parameters in the Resource
        Manager once satisfied. Suck-back speed is fixed at SUCK_BACK_SPEED_ML_PER_MIN.

        Constraints:
            suck_back_volume_ml: 0.004 mL <= value <= dispense_volume_ml
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
            self.high_viscosity_dispenser.suck_back(suck_back_volume_ml, delay_s=suck_back_delay_s)
            return ActionSucceeded(json_result={
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
                "dispense_volume_ml": dispense_volume_ml,
                "dispense_speed_ml_per_min": dispense_speed_ml_per_min,
                "suck_back_delay_s": suck_back_delay_s,
                "suck_back_volume_ml": suck_back_volume_ml,
            })
        except Exception as e:
            return ActionFailed(errors=[e])


if __name__ == "__main__":
    node = HighViscosityLiquidWeighingNode()
    node.start_node()
