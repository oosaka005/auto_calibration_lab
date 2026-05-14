"""Human-in-the-loop node for operator review and approval steps."""

import logging
import time
from typing import Any, ClassVar

from madsci.common.types.admin_command_types import AdminCommandResponse
from madsci.common.types.node_types import RestNodeConfig
from madsci.node_module.rest_node_module import RestNode


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

    def startup_handler(self) -> None:
        """No devices to connect."""
        self.logger.log("HumanNode: startup complete")

    def shutdown_handler(self) -> None:
        """No devices to close."""
        self.logger.log("HumanNode: shutdown complete")

    def state_handler(self) -> dict[str, Any]:
        """Report current node state.

        Called automatically every ~2 seconds (state_update_interval).
        """
        self.node_state = {
            "status": "waiting_for_approval" if self.node_status.paused else "idle",
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

    # Actions to be implemented here.
    # Example: review_and_save_calibration(material_name, pressure_mpa, calibration_result)


if __name__ == "__main__":
    node = HumanNode()
    node.start_node()
