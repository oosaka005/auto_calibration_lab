"""Human-in-the-loop node for operator review and approval steps."""

import logging
import statistics
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Optional

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import requests
from madsci.common.types.action_types import ActionFailed, ActionSucceeded, ActionResult
from madsci.common.types.admin_command_types import AdminCommandResponse
from madsci.common.types.node_types import RestNodeConfig
from madsci.node_module.helpers import action
from madsci.node_module.rest_node_module import RestNode

matplotlib.use("Agg")  # non-interactive backend (no display required in container)


class HumanNodeConfig(
    RestNodeConfig,
    yaml_file=("settings.yaml", "node.settings.yaml"),
):
    """Configuration for the human node.

    No device connections — operator interaction only.
    """

    DEVICE_CLASSES: ClassVar[dict] = {}

    # --- Node-specific operation parameters (add here when needed) ---


class HumanNode(RestNode):
    """Human-in-the-loop node.

    Pauses workflow execution to allow an operator to review results and
    approve before proceeding. Operator resumes via the Squid Dashboard
    node card Resume button.
    """

    config: HumanNodeConfig = HumanNodeConfig()
    config_model = HumanNodeConfig

    # No device instance fields — DEVICE_CLASSES is empty.

    # Last datapoint_id uploaded by this node (shown in node_state while paused).
    _last_datapoint_id: Optional[str] = None

    def startup_handler(self) -> None:
        """No devices to connect."""
        self.logger.log("HumanNode: startup complete")

    def shutdown_handler(self) -> None:
        """No devices to close."""
        self.logger.log("HumanNode: shutdown complete")

    def state_handler(self) -> dict[str, Any]:
        """Report current node state."""
        self.node_state = {
            "status": "waiting_for_approval" if self.node_status.paused else "idle",
        }
        if self.node_status.paused and self._last_datapoint_id:
            self.node_state["last_plot_datapoint_id"] = self._last_datapoint_id
            self.node_state["hint"] = (
                f"Open .madsci/datapoints/ and find file with ID prefix "
                f"{self._last_datapoint_id[:8]}, then press Resume to proceed."
            )

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
        """Pause — wait for operator approval."""
        self.node_status.paused = True
        return AdminCommandResponse()

    def resume(self) -> AdminCommandResponse:
        """Resume after operator approval."""
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
    #     """Emergency stop. Implement when physical safety devices are connected."""
    #     # self.node_status.stopped = True
    #     return AdminCommandResponse()

    # def get_location(self) -> AdminCommandResponse:
    #     """Return physical coordinates of this node. Mainly used for robot arm nodes."""
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

    # mL per revolution — device constant (matches dispenser_check notebook)
    _ML_PER_REV: float = 0.05

    @action
    def generate_calibration_plot(self, calibration_result: dict) -> dict:
        """Generate a calibration plot and upload it to the Data Manager.

        Reproduces the dual-axis bar+line chart from dispenser_check.ipynb:
          Left axis  (blue bars)  : measured dispensing rate [g/min]
          Right axis (green line) : measured density [g/cm³]
        Throughput and accuracy operating points are highlighted.
        Nominal density and min_shot info are looked up from the Resource Manager.
        """
        try:
            jr = calibration_result
            results = jr.get("calibration_results", [])
            material_name = jr.get("material_name", "unknown")
            pressure_mpa = jr.get("pressure_mpa", "?")
            throughput_speed = jr["throughput"]["speed_ml_per_min"]
            throughput_density = jr["throughput"]["density_g_per_cm3"]
            accuracy_speed = jr["accuracy"]["speed_ml_per_min"]
            accuracy_density = jr["accuracy"]["density_g_per_cm3"]

            speeds = [r["speed_ml_per_min"] for r in results]
            densities = [r["density_g_per_cm3"] for r in results]
            rpms = [s / self._ML_PER_REV for s in speeds]
            g_per_min = [d * s for d, s in zip(densities, speeds)]
            throughput_idx = speeds.index(throughput_speed)
            accuracy_idx = speeds.index(accuracy_speed)
            throughput_rpm = rpms[throughput_idx]
            accuracy_rpm = rpms[accuracy_idx]
            throughput_g_per_min = throughput_density * throughput_speed
            accuracy_g_per_min = accuracy_density * accuracy_speed

            # Resource Manager lookup for nominal density and min_shot
            nominal_density = None
            min_shot_mass_mg = None
            try:
                mat = self.resource_client.query_resource(resource_name=material_name)
                attrs = mat.attributes or {}
                nominal_density = attrs.get("physical_properties_nominal", {}).get("density_g_per_cm3")
                pressure_key = f"{pressure_mpa}MPa"
                min_shot_mass_mg = (
                    attrs.get("dispensing_params", {})
                    .get("high_viscosity_dispenser", {})
                    .get(pressure_key, {})
                    .get("min_shot", {})
                    .get("measured_mass_mg")
                )
            except Exception:
                pass
            min_shot_str = f"{min_shot_mass_mg} mg" if min_shot_mass_mg is not None else "Not measured"

            # Y-axis ranges
            left_all = list(g_per_min)
            if nominal_density is not None:
                left_all += [nominal_density * rpm * self._ML_PER_REV for rpm in rpms]
            left_min = max(0.0, min(left_all) * 0.9)
            left_max = max(left_all) * 1.1
            right_all = list(densities)
            if nominal_density is not None:
                right_all.append(nominal_density)
            right_min = min(right_all) * 0.9
            right_max = max(right_all) * 1.1

            bar_colors = ["steelblue"] * len(rpms)
            bar_colors[throughput_idx] = "orangered"
            if accuracy_idx != throughput_idx:
                bar_colors[accuracy_idx] = "gold"

            fig, ax1 = plt.subplots(figsize=(10, 6))
            fig.subplots_adjust(bottom=0.30, right=0.95)
            ax2 = ax1.twinx()

            bar_width = (rpms[-1] - rpms[0]) / len(rpms) * 0.6 if len(rpms) > 1 else 5.0
            bars = ax1.bar(rpms, g_per_min, width=bar_width, color=bar_colors, alpha=0.75)
            label_offset = (left_max - left_min) * 0.015
            for bar, val in zip(bars, g_per_min):
                ax1.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + label_offset,
                    f"{val:.2f} g/min",
                    ha="center", va="bottom", fontsize=8.5,
                )

            if nominal_density is not None:
                target_g_min = [nominal_density * rpm * self._ML_PER_REV for rpm in rpms]
                ax1.plot(
                    rpms, target_g_min,
                    color="steelblue", linestyle="--", linewidth=1.4, marker="o", markersize=6,
                    markeredgecolor="white", markeredgewidth=0.8,
                    label=f"Target dispensing rate (nominal: {nominal_density:.3f} g/cm³)",
                )

            ax2.plot(rpms, densities, color="green", marker="o", linewidth=1.8, linestyle="-",
                     label="Density (measured)")
            ax2.plot(throughput_rpm, throughput_density, marker="*", color="orangered",
                     markersize=14, zorder=6,
                     label=f"Throughput: {throughput_density:.3f} g/cm³ @ {throughput_rpm:.0f} rpm")
            ax2.plot(accuracy_rpm, accuracy_density, marker="D", color="gold",
                     markersize=10, zorder=6, markeredgecolor="gray",
                     label=f"Accuracy: {accuracy_density:.3f} g/cm³ @ {accuracy_rpm:.0f} rpm")
            if nominal_density is not None:
                ax2.axhline(nominal_density, color="green", linestyle="--", linewidth=1.4,
                            label=f"Nominal density: {nominal_density:.3f} g/cm³")

            ax1.set_xlabel("Screw Rotation Speed [rpm]", fontsize=11)
            ax1.set_ylabel("Dispensing Rate [g/min]", fontsize=11, color="steelblue")
            ax1.tick_params(axis="y", colors="steelblue")
            ax1.yaxis.label.set_color("steelblue")
            ax2.set_ylabel("Density [g/cm³]", fontsize=11, color="green")
            ax2.tick_params(axis="y", colors="green")
            ax2.yaxis.label.set_color("green")
            ax1.set_ylim(left_min, left_max)
            ax2.set_ylim(right_min, right_max)
            ax1.set_xticks(rpms)
            ax1.set_title(f"{material_name} @ {pressure_mpa} MPa", fontsize=12)

            info = (
                f"Throughput: {throughput_rpm:.0f} rpm, {throughput_g_per_min:.2f} g/min, "
                f"density={throughput_density:.3f} g/cm³\n"
                f"Accuracy:   {accuracy_rpm:.0f} rpm, {accuracy_g_per_min:.2f} g/min, "
                f"density={accuracy_density:.3f} g/cm³\n"
                f"min_shot (manual): {min_shot_str}"
            )
            ax1.text(
                0.02, 0.98, info, transform=ax1.transAxes,
                fontsize=9, va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.9),
            )

            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            patch_tp = mpatches.Patch(color="orangered", alpha=0.85,
                                      label=f"Throughput: {throughput_rpm:.0f} rpm, {throughput_g_per_min:.2f} g/min")
            patch_ac = mpatches.Patch(color="gold", alpha=0.85,
                                      label=f"Accuracy: {accuracy_rpm:.0f} rpm, {accuracy_g_per_min:.2f} g/min")
            patch_rest = mpatches.Patch(color="steelblue", alpha=0.85, label="Other speed")
            ax1.legend(
                [patch_tp, patch_ac, patch_rest] + lines1 + lines2,
                [patch_tp.get_label(), patch_ac.get_label(), patch_rest.get_label()] + labels1 + labels2,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.18),
                bbox_transform=ax1.transAxes,
                ncol=2, fontsize=8, framealpha=0.9,
            )

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                plot_path = Path(f.name)
            fig.savefig(plot_path, dpi=150)
            plt.close(fig)

            datapoint_id = self.create_and_upload_file_datapoint(
                file_path=plot_path,
                label="calibration_plot",
            )
            plot_path.unlink()
            self._last_datapoint_id = datapoint_id

            return ActionSucceeded(json_result={
                "datapoint_id": datapoint_id,
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
            })
        except Exception as e:
            return ActionFailed(errors=[e])

    @action
    def wait_for_approval(self) -> ActionResult:
        """Pause and wait for operator approval.

        The node blocks here until the operator presses Resume on the
        Squid Dashboard node card. To abort, use the Cancel button on
        the workflow instead.
        """
        try:
            self.pause()
            self._checkpoint()
            return ActionSucceeded()
        except Exception as e:
            return ActionFailed(errors=[e])

    @action
    def save_calibration_to_resource(self, calibration_result: dict) -> ActionResult:
        """Save calibration results to the Resource Manager.

        Writes throughput and accuracy (speed + density) for the given
        material and pressure into dispensing_params.high_viscosity_dispenser.
        Sets source_type="workflow" and calibrated_at to the current time.
        """
        try:
            material_name = calibration_result["material_name"]
            pressure_mpa = calibration_result["pressure_mpa"]
            pressure_key = f"{pressure_mpa}MPa"

            try:
                material = self.resource_client.query_resource(resource_name=material_name)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    return ActionFailed(
                        errors=[ValueError(f"Material '{material_name}' not found in Resource Manager")]
                    )
                return ActionFailed(errors=[e])

            attrs = material.attributes or {}
            dispensing_params = attrs.setdefault("dispensing_params", {})
            device_params = dispensing_params.setdefault("high_viscosity_dispenser", {})
            pressure_params = device_params.setdefault(pressure_key, {})

            pressure_params["throughput"] = {
                "speed_ml_per_min": calibration_result["throughput"]["speed_ml_per_min"],
                "density_g_per_cm3": calibration_result["throughput"]["density_g_per_cm3"],
            }
            pressure_params["accuracy"] = {
                "speed_ml_per_min": calibration_result["accuracy"]["speed_ml_per_min"],
                "density_g_per_cm3": calibration_result["accuracy"]["density_g_per_cm3"],
            }
            pressure_params["calibrated_at"] = datetime.now().isoformat()
            pressure_params["source_type"] = "workflow"
            pressure_params["source_datapoint_id"] = None

            material.attributes = attrs
            self.resource_client.update_resource(material)

            return ActionSucceeded()
        except Exception as e:
            return ActionFailed(errors=[e])

    @action
    def generate_dispense_plot(self, batch_result: dict) -> dict:
        """Generate a parity plot (log scale) from dispense_batch results.

        Reproduces the parity plot from dispenser_check.ipynb (cell 3-6-3):
          - Log-scale scatter of target vs. measured mass
          - Per-point annotation with Target / Measured / Error% / Time
          - Summary table below the chart
        batch_result: json_result of dispense_batch.
          Must contain key "dispense_results" (list of per-point dicts).
        """
        try:
            import matplotlib.gridspec as gridspec

            dispense_results = batch_result.get("dispense_results", [])
            material_name = batch_result.get("material_name", "unknown")
            pressure_mpa = batch_result.get("pressure_mpa", "?")
            targets = [r["target_mass_g"] for r in dispense_results]
            actuals = [r["measured_mass_g"] for r in dispense_results]
            times = [r.get("elapsed_s", 0.0) for r in dispense_results]
            errors = [a - t for a, t in zip(actuals, targets)]
            err_pcts = [e / t * 100 for e, t in zip(errors, targets)]

            pt_color = "#00aadd"
            fig = plt.figure(figsize=(8, 10))
            gs = gridspec.GridSpec(2, 1, height_ratios=[3.5, 1.0], hspace=0.45)

            ax1 = fig.add_subplot(gs[0])
            lo = min(targets) * 0.5
            hi = max(targets) * 2.0
            ideal = np.logspace(np.log10(lo), np.log10(hi), 400)
            ax1.plot(ideal, ideal, color="gray", linestyle="--", linewidth=1.6, label="Ideal  y = x")
            ax1.scatter(targets, actuals, color=pt_color, s=110, zorder=5,
                        label="Measured", edgecolors="white", linewidth=1.2)
            for t, a, pct, t_s in zip(targets, actuals, err_pcts, times):
                ax1.annotate(
                    f"T: {t:g} g  →  M: {a:.3f} g\n{pct:+.2f}%  /  {t_s:.1f} sec",
                    xy=(t, a), xytext=(t * 1.12, a * 0.97),
                    fontsize=9, fontweight="bold", color="#333333",
                    va="top", ha="left", linespacing=1.4,
                    arrowprops=dict(arrowstyle="-", color="lightgray", lw=0.8),
                )
            ax1.set_xscale("log")
            ax1.set_yscale("log")
            ax1.set_xlim(lo, hi)
            ax1.set_ylim(lo, hi)
            tick_vals = sorted({10 ** round(np.log10(v)) for v in targets})
            ax1.set_xticks(tick_vals)
            ax1.set_yticks(tick_vals)
            ax1.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
            ax1.set_xlabel("Target Mass [g]", fontsize=12, fontweight="bold")
            ax1.set_ylabel("Measured Mass [g]", fontsize=12, fontweight="bold")
            ax1.set_title(
                f"Parity Plot (Log Scale) — {material_name}  ({pressure_mpa} MPa)",
                fontsize=12, fontweight="bold",
            )
            ax1.legend(fontsize=9, loc="upper left")
            ax1.tick_params(labelsize=10)
            ax1.set_aspect("equal", adjustable="box")

            ax_tbl = fig.add_subplot(gs[1])
            ax_tbl.axis("off")
            col_labels = ["#", "Target [g]", "Measured [g]", "Error [g]", "Error [%]", "Time [s]"]
            rows = []
            for i, r in enumerate(dispense_results):
                err = r["measured_mass_g"] - r["target_mass_g"]
                pct = err / r["target_mass_g"] * 100
                rows.append([
                    str(i + 1),
                    f"{r['target_mass_g']:.3f}",
                    f"{r['measured_mass_g']:.3f}",
                    f"{err:+.3f}",
                    f"{pct:+.2f}%",
                    f"{r.get('elapsed_s', 0.0):.1f}",
                ])
            tbl = ax_tbl.table(cellText=rows, colLabels=col_labels, loc="center", cellLoc="center")
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(10)
            tbl.scale(1, 1.6)
            for col in range(len(col_labels)):
                tbl[(0, col)].set_facecolor("#cce0ff")
                tbl[(0, col)].set_text_props(fontweight="bold", fontsize=10)

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                plot_path = Path(f.name)
            fig.savefig(plot_path, dpi=150)
            plt.close(fig)

            datapoint_id = self.create_and_upload_file_datapoint(
                file_path=plot_path,
                label="dispense_plot",
            )
            plot_path.unlink()
            self._last_datapoint_id = datapoint_id

            return ActionSucceeded(json_result={
                "datapoint_id": datapoint_id,
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
                "n_points": len(dispense_results),
            })
        except Exception as e:
            return ActionFailed(errors=[e])

    @action
    def generate_dispense_repeatability_plot(self, repeatability_result: dict) -> dict:
        """Generate a review plot for dispense repeatability results.

        The plot shows each measured mass as grouped bars by target mass.
        Mean error percent is shown on the secondary axis. Tables below the
        plot show per-repeat results and summary metrics: mean error percent,
        CV percent, and average elapsed time.
        """
        try:
            import matplotlib.gridspec as gridspec

            material_name = repeatability_result.get("material_name", "unknown")
            pressure_mpa = repeatability_result.get("pressure_mpa", "?")
            repeat_count = repeatability_result.get("repeat_count", "?")
            results = repeatability_result.get("results", [])
            if not results:
                return ActionFailed(errors=[ValueError("repeatability_result contains no results.")])

            target_masses = repeatability_result.get("target_masses_g")
            if not target_masses:
                target_masses = sorted({float(r["target_mass_g"]) for r in results})
            target_masses = [float(target_mass_g) for target_mass_g in target_masses]

            grouped = {}
            for target_mass_g in target_masses:
                grouped[target_mass_g] = [
                    r for r in results
                    if float(r["target_mass_g"]) == target_mass_g
                    and r.get("measured_mass_g") is not None
                ]

            summary_rows = []
            raw_rows = []
            for target_mass_g in target_masses:
                rows = grouped[target_mass_g]
                masses = [float(r["measured_mass_g"]) for r in rows]
                if not masses:
                    continue
                mean_mass_g = statistics.fmean(masses)
                stdev_mass_g = statistics.stdev(masses) if len(masses) > 1 else 0.0
                mean_error_percent = statistics.fmean(
                    [(mass_g - target_mass_g) / target_mass_g * 100.0 for mass_g in masses]
                )
                elapsed_values = [
                    float(r.get("elapsed_s", 0.0))
                    for r in rows
                    if r.get("elapsed_s") is not None
                ]
                mean_elapsed_s = statistics.fmean(elapsed_values) if elapsed_values else None
                cv_percent = (
                    stdev_mass_g / abs(mean_mass_g) * 100.0
                    if mean_mass_g != 0
                    else None
                )
                summary_rows.append([
                    f"{target_mass_g:g}",
                    str(len(masses)),
                    f"{mean_mass_g:.5g}",
                    f"{mean_error_percent:+.2f}",
                    f"{cv_percent:.2f}" if cv_percent is not None else "n/a",
                    f"{mean_elapsed_s:.1f}" if mean_elapsed_s is not None else "n/a",
                ])
                for r in rows:
                    measured_mass_g = float(r["measured_mass_g"])
                    error_percent = (measured_mass_g - target_mass_g) / target_mass_g * 100.0
                    raw_rows.append([
                        f"{target_mass_g:g}",
                        str(r.get("repeat_index", "")),
                        f"{measured_mass_g:.5g}",
                        f"{error_percent:+.2f}",
                        f"{float(r.get('elapsed_s', 0.0)):.1f}" if r.get("elapsed_s") is not None else "n/a",
                    ])

            if not summary_rows:
                return ActionFailed(errors=[ValueError("No valid measured_mass_g values found.")])

            plot_height = 4.8
            summary_table_height = max(1.0, 0.32 * (len(summary_rows) + 1))
            raw_table_height = max(1.8, 0.24 * (len(raw_rows) + 1))
            fig_height = plot_height + summary_table_height + raw_table_height + 1.2
            fig = plt.figure(figsize=(10, fig_height))
            gs = gridspec.GridSpec(
                3, 1,
                height_ratios=[plot_height, summary_table_height, raw_table_height],
                hspace=0.55,
            )

            ax = fig.add_subplot(gs[0])
            ax_error = ax.twinx()
            x_positions = np.arange(len(target_masses), dtype=float)
            max_repeats = max(len(grouped[target_mass_g]) for target_mass_g in target_masses)
            bar_width = min(0.18, 0.72 / max(max_repeats, 1))
            measured_color = "#6baed6"
            target_color = "#333333"
            error_color = "#cc3311"

            all_masses = [
                float(r["measured_mass_g"])
                for target_mass_g in target_masses
                for r in grouped[target_mass_g]
                if r.get("measured_mass_g") is not None
            ]
            mean_error_percents = []
            use_log_y = (
                all(mass_g > 0 for mass_g in all_masses + target_masses)
                and max(all_masses + target_masses) / min(all_masses + target_masses) > 20
            )
            bar_bottom = min(all_masses + target_masses) * 0.5 if use_log_y else 0.0

            for x_pos, target_mass_g in zip(x_positions, target_masses):
                rows = sorted(grouped[target_mass_g], key=lambda r: r.get("repeat_index", 0))
                masses = [float(r["measured_mass_g"]) for r in rows]
                if not masses:
                    continue
                offsets = (
                    (np.arange(len(masses)) - (len(masses) - 1) / 2.0) * bar_width
                )
                ax.bar(
                    x_pos + offsets,
                    [mass_g - bar_bottom for mass_g in masses],
                    width=bar_width * 0.88,
                    bottom=bar_bottom,
                    color=measured_color,
                    edgecolor="white",
                    linewidth=0.8,
                    alpha=0.9,
                    label="Measured mass" if x_pos == 0 else None,
                )
                ax.hlines(
                    target_mass_g,
                    x_pos - 0.42,
                    x_pos + 0.42,
                    color=target_color,
                    linestyle="--",
                    linewidth=1.8,
                    zorder=4,
                    label="Target mass" if x_pos == 0 else None,
                )
                mean_error_percent = statistics.fmean(
                    [(mass_g - target_mass_g) / target_mass_g * 100.0 for mass_g in masses]
                )
                mean_error_percents.append(mean_error_percent)
                ax_error.plot(
                    [x_pos],
                    [mean_error_percent],
                    color=error_color,
                    marker="o",
                    markersize=7,
                    linestyle="None",
                    zorder=6,
                    label="Mean error [%]" if x_pos == 0 else None,
                )
                ax_error.annotate(
                    f"{mean_error_percent:+.2f}%",
                    xy=(x_pos, mean_error_percent),
                    xytext=(6, 0),
                    textcoords="offset points",
                    va="center",
                    ha="left",
                    fontsize=8,
                    color=error_color,
                    zorder=7,
                )

            if use_log_y:
                ax.set_yscale("log")

            ax_error.axhline(0.0, color=error_color, linestyle="--", linewidth=1.0, alpha=0.5)
            max_abs_mean_error = max(abs(v) for v in mean_error_percents) if mean_error_percents else 1.0
            error_limit = max(1.0, max_abs_mean_error * 1.25)
            ax_error.set_ylim(-error_limit, error_limit)
            ax.set_xticks(x_positions)
            ax.set_xticklabels([f"{target_mass_g:g}" for target_mass_g in target_masses])
            ax.set_xlabel("Target mass [g]", fontsize=11)
            ax.set_ylabel("Measured mass [g]", fontsize=11)
            ax_error.set_ylabel("Mean error [%]", fontsize=11, color=error_color)
            ax_error.tick_params(axis="y", colors=error_color)
            ax.set_title(
                f"Dispense Repeatability - {material_name} ({pressure_mpa} MPa, n={repeat_count})",
                fontsize=12,
                fontweight="bold",
            )
            ax.grid(True, axis="y", alpha=0.25)
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax_error.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=9)

            ax_summary = fig.add_subplot(gs[1])
            ax_summary.axis("off")
            summary_labels = [
                "Target [g]",
                "n",
                "Mean measured [g]",
                "Mean error [%]",
                "CV [%]",
                "Avg time [s]",
            ]
            summary_table = ax_summary.table(
                cellText=summary_rows,
                colLabels=summary_labels,
                loc="center",
                cellLoc="center",
                bbox=[0.0, 0.0, 1.0, 1.0],
            )
            summary_table.auto_set_font_size(False)
            summary_table.set_fontsize(9)
            for col in range(len(summary_labels)):
                summary_table[(0, col)].set_facecolor("#cce0ff")
                summary_table[(0, col)].set_text_props(fontweight="bold")

            ax_raw = fig.add_subplot(gs[2])
            ax_raw.axis("off")
            raw_labels = ["Target [g]", "Repeat", "Measured [g]", "Error [%]", "Time [s]"]
            raw_table = ax_raw.table(
                cellText=raw_rows,
                colLabels=raw_labels,
                loc="center",
                cellLoc="center",
                bbox=[0.0, 0.0, 1.0, 1.0],
            )
            raw_table.auto_set_font_size(False)
            raw_font_size = 8 if len(raw_rows) <= 30 else 7
            raw_table.set_fontsize(raw_font_size)
            for col in range(len(raw_labels)):
                raw_table[(0, col)].set_facecolor("#e6e6e6")
                raw_table[(0, col)].set_text_props(fontweight="bold")

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                plot_path = Path(f.name)
            fig.savefig(plot_path, dpi=150, bbox_inches="tight")
            plt.close(fig)

            datapoint_id = self.create_and_upload_file_datapoint(
                file_path=plot_path,
                label="dispense_repeatability_plot",
            )
            plot_path.unlink()
            self._last_datapoint_id = datapoint_id

            return ActionSucceeded(json_result={
                "datapoint_id": datapoint_id,
                "material_name": material_name,
                "pressure_mpa": pressure_mpa,
                "n_points": len(raw_rows),
            })
        except Exception as e:
            return ActionFailed(errors=[e])


if __name__ == "__main__":
    node = HumanNode()
    node.start_node()
