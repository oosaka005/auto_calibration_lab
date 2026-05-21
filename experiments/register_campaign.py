"""Campaign registration script.

Registers a new campaign in the Experiment Manager and issues a campaign_id.
No need to re-run if continuing an existing campaign.

Usage:
    python experiments/register_campaign.py

Requirements:
    Docker services must be running:
        docker compose up -d madsci_mongo event_manager experiment_manager

Output:
    Prints the campaign_id.
    Copy it into the CAMPAIGN_ID constant in the target experiments/*.py script.
"""

from madsci.client.experiment_client import ExperimentClient
from madsci.common.types.experiment_types import ExperimentalCampaign

# ---------------------------------------------------------------------------
# Campaign info — edit before running
# ---------------------------------------------------------------------------

CAMPAIGN_NAME = "Test campaign"
"""
Examples:
  "High-Viscosity Material Calibration 2026 Q1"
  "Thermal Grease Optimal Formulation Search 2026 Q2"
"""

CAMPAIGN_DESCRIPTION = """
Functional verification campaign using real hardware.
Tests end-to-end operation of the high-viscosity dispenser calibration workflow,
including gravimetric calibration and dispense accuracy measurement,
to confirm that all system components work correctly on the actual physical setup.
"""

# ---------------------------------------------------------------------------
# Experiment Manager URL
# ---------------------------------------------------------------------------

EXPERIMENT_MANAGER_URL = "http://localhost:8002/"

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ec = ExperimentClient(experiment_server_url=EXPERIMENT_MANAGER_URL)

    campaign = ec.register_campaign(
        ExperimentalCampaign(
            campaign_name=CAMPAIGN_NAME,
            campaign_description=CAMPAIGN_DESCRIPTION.strip(),
            experiment_ids=[],
        )
    )

    campaign_id = campaign["campaign_id"]

    print("=" * 60)
    print("Campaign registered successfully")
    print("=" * 60)
    print(f"  campaign_name : {CAMPAIGN_NAME}")
    print(f"  campaign_id   : {campaign_id}")
    print("=" * 60)
    print()
    print("Copy the following into the target experiments/*.py script:")
    print()
    print(f'  CAMPAIGN_ID = "{campaign_id}"')
    print()
    print("Example ExperimentDesign configuration:")
    print()
    print("  from madsci.common.types.auth_types import OwnershipInfo")
    print()
    print("  experiment_design = ExperimentDesign(")
    print('      experiment_name="...",')
    print(f'      ownership_info=OwnershipInfo(campaign_id="{campaign_id}"),')
    print("  )")
