import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from .models import Incident, EmergencyStatus, ChangeType, StatusPriority
from .config import Config


class StatusTracker:
    """Tracks incident status changes between polls"""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or Config.STATE_FILE
        self._previous_states: Dict[int, dict] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load previous state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self._previous_states = {
                        int(k): v for k, v in data.get("incidents", {}).items()
                    }
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load state file: {e}")
                self._previous_states = {}

    def _save_state(self) -> None:
        """Save current state to file"""
        Config.ensure_data_dir()
        with open(self.state_file, "w") as f:
            json.dump(
                {
                    "last_updated": datetime.now().isoformat(),
                    "incidents": self._previous_states,
                },
                f,
                indent=2,
            )

    def _get_status_priority(self, status: str) -> int:
        """Get priority value for a status (lower = more severe)"""
        status_upper = status.upper()
        try:
            return StatusPriority[status_upper].value
        except KeyError:
            return 5  # Unknown status gets lowest priority

    def detect_change(
        self, incident_no: int, current_status: str
    ) -> Tuple[ChangeType, Optional[str]]:
        """Detect if status has changed and what type of change"""
        previous = self._previous_states.get(incident_no)

        if previous is None:
            return ChangeType.NEW, None

        previous_status = previous.get("origin_status", "")

        if current_status.upper() == "SAFE" and previous_status.upper() != "SAFE":
            return ChangeType.RESOLVED, previous_status

        current_priority = self._get_status_priority(current_status)
        previous_priority = self._get_status_priority(previous_status)

        if current_priority < previous_priority:
            # Lower number = more severe = UPGRADE (escalation)
            return ChangeType.UPGRADE, previous_status
        elif current_priority > previous_priority:
            # Higher number = less severe = DOWNGRADE (de-escalation)
            return ChangeType.DOWNGRADE, previous_status

        return ChangeType.NONE, previous_status

    def update_state(self, incidents: List[Incident]) -> None:
        """Update stored state with current incidents"""
        current_incident_nos = set()

        for incident in incidents:
            current_incident_nos.add(incident.incident_no)
            self._previous_states[incident.incident_no] = {
                "origin_status": incident.origin_status,
                "incident_status": incident.incident_status,
                "category2": incident.category2,
                "location": incident.location,
                "last_update": incident.last_update,
                "last_seen": datetime.now().isoformat(),
            }

        # Mark incidents no longer in feed as resolved (keep for 24 hours)
        stale_threshold = datetime.now().timestamp() - (24 * 60 * 60)
        to_remove = []
        for incident_no, state in self._previous_states.items():
            if incident_no not in current_incident_nos:
                last_seen = state.get("last_seen", "")
                if last_seen:
                    try:
                        last_seen_dt = datetime.fromisoformat(last_seen)
                        if last_seen_dt.timestamp() < stale_threshold:
                            to_remove.append(incident_no)
                    except ValueError:
                        to_remove.append(incident_no)

        for incident_no in to_remove:
            del self._previous_states[incident_no]

        self._save_state()

    def get_resolved_incidents(
        self, current_incident_nos: set
    ) -> List[Tuple[int, dict]]:
        """Get incidents that were in previous state but not in current"""
        resolved = []
        for incident_no, state in self._previous_states.items():
            if incident_no not in current_incident_nos:
                resolved.append((incident_no, state))
        return resolved
