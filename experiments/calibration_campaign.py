"""Calibration campaign experiment script.

Runs the full dispenser calibration + gravimetric accuracy test workflow
for one or more materials using the MADSci ExperimentScript framework.

Usage (single run):
    python calibration_campaign.py

Usage (campaign — iterate over multiple materials):
    Modify MATERIALS_TO_CALIBRATE below and run the same command.

Requirements:
    Docker services must be running:
        docker compose up -d
"""

from pathlib import Path

from madsci.common.types.experiment_types import ExperimentDesign
from madsci.experiment_application.experiment_script import ExperimentScript

# ---------------------------------------------------------------------------
# Campaign parameters — edit here before running
# ---------------------------------------------------------------------------

WORKFLOW_PATH = str(
    Path(__file__).parent.parent / "workflows" / "calibration_and_accuracy_test.workflow.yaml"
)

# Target masses for the gravimetric accuracy test.
# Based on dispenser_check.ipynb: logarithmically spaced from min-shot to ~1 g.
DEFAULT_TARGET_MASSES_G = [0.010, 0.032, 0.100, 0.316, 1.000]

# List of materials to calibrate in sequence.
# Each entry is a dict matching the workflow's json_inputs.
# Add / remove entries to run a multi-material campaign.
MATERIALS_TO_CALIBRATE = [
    {
        "material_name": "エポキシ樹脂A",       # Must match resource_name in Resource Manager
        "pressure_mpa": 0.1,
        "volume_per_step_ml": 1.0,
        "speed_start_ml_per_min": 1.0,
        "speed_end_ml_per_min": 10.0,
        "speed_step_ml_per_min": 1.0,
        "target_masses_g": DEFAULT_TARGET_MASSES_G,
    },
    # Add more materials here, e.g.:
    # {
    #     "material_name": "硬化剤B",
    #     "pressure_mpa": 0.1,
    #     "volume_per_step_ml": 1.0,
    #     "speed_start_ml_per_min": 1.0,
    #     "speed_end_ml_per_min": 8.0,
    #     "speed_step_ml_per_min": 1.0,
    #     "target_masses_g": DEFAULT_TARGET_MASSES_G,
    # },
]


# ---------------------------------------------------------------------------
# Experiment class
# ---------------------------------------------------------------------------


class CalibrationCampaign(ExperimentScript):
    """Run dispenser calibration + accuracy test for one or more materials.

    For each material in MATERIALS_TO_CALIBRATE, this script:
      1. Submits the calibration_and_accuracy_test workflow.
      2. Waits for it to complete (human-in-the-loop steps pause it mid-run).
      3. Collects the workflow result and logs it.
      4. Moves on to the next material.
    """

    experiment_design = ExperimentDesign(
        experiment_name="Dispenser Calibration Campaign",
        experiment_description=(
            "Calibrate the high-viscosity dispenser for each registered material "
            "and verify gravimetric accuracy across multiple target masses."
        ),
    )

    def run_experiment(self) -> dict:
        """Run calibration for all materials listed in MATERIALS_TO_CALIBRATE."""
        campaign_results = {}

        for params in MATERIALS_TO_CALIBRATE:
            material_name = params["material_name"]
            self.logger.info(f"Starting calibration for: {material_name}")

            # Submit and wait for the workflow to complete.
            # The workflow will pause twice for human review (wait_for_approval).
            # Resume each pause via the Workcell Manager REST API or dashboard.
            workflow = self.workcell_client.start_workflow(
                WORKFLOW_PATH,
                json_inputs=params,
            )

            self.logger.info(
                f"Workflow completed for {material_name}. "
                f"Workflow ID: {workflow.workflow_id}"
            )

            # Retrieve the dispense accuracy test result from the workflow's
            # Data Manager datapoints (step key = "generate_dispense_plot").
            try:
                datapoint = workflow.get_datapoint(step_key="generate_dispense_plot")
                campaign_results[material_name] = {
                    "workflow_id": workflow.workflow_id,
                    "dispense_plot_datapoint_id": datapoint.datapoint_id if datapoint else None,
                }
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    f"Could not retrieve dispense plot datapoint for {material_name}: {exc}"
                )
                campaign_results[material_name] = {
                    "workflow_id": workflow.workflow_id,
                    "dispense_plot_datapoint_id": None,
                }

        self.logger.info("Campaign complete.")
        return campaign_results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # lab_server_url points to the MADSci Lab Manager (squid), which
    # auto-discovers all other manager URLs from settings.yaml.
    # If running without squid, set individual manager URLs directly:
    #   CalibrationCampaign(
    #       workcell_server_url="http://localhost:8005",
    #       experiment_server_url="http://localhost:8002",
    #   ).run()
    CalibrationCampaign().run()
