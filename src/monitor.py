import json
import csv
import io
from datetime import datetime
from typing import List, Optional
from tabulate import tabulate

from .models import Incident, EmergencyStatus, ChangeType
from .api_client import VicEmergencyClient
from .geocoder import PostcodeGeocoder
from .status_tracker import StatusTracker
from .config import Config


class VicEmergencyMonitor:
    """Main monitor class that orchestrates the emergency tracking"""

    def __init__(self):
        self.client = VicEmergencyClient()
        self.geocoder = PostcodeGeocoder()
        self.tracker = StatusTracker()

    def _resolve_postcode(self, incident: Incident) -> str:
        """Resolve postcode from incident location/coordinates"""
        return self.geocoder.resolve_postcode(
            location=incident.location,
            latitude=incident.latitude,
            longitude=incident.longitude,
            municipality=incident.municipality,
        )

    def _build_type_string(self, incident: Incident) -> str:
        """Build the Type field: {IncidentStatus} - {Category2} - {OriginStatus}"""
        parts = []

        if incident.incident_status:
            parts.append(incident.incident_status)

        if incident.category2:
            parts.append(incident.category2)

        if incident.origin_status:
            parts.append(incident.origin_status)

        return " - ".join(parts) if parts else "Unknown"

    def _parse_update_time(self, time_str: str) -> datetime:
        """Parse the API timestamp format"""
        if not time_str:
            return datetime.now()

        # Format: "DD/MM/YYYY HH:MM:SS"
        try:
            return datetime.strptime(time_str, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            return datetime.now()

    def process_incidents(
        self, incidents: List[Incident]
    ) -> List[EmergencyStatus]:
        """Process incidents and return emergency statuses"""
        statuses: List[EmergencyStatus] = []

        for incident in incidents:
            # Detect status change
            change_type, previous_status = self.tracker.detect_change(
                incident.incident_no, incident.origin_status
            )

            # Resolve postcode
            postcode = self._resolve_postcode(incident)

            # Build output record
            status = EmergencyStatus(
                postcode=postcode,
                type=self._build_type_string(incident),
                location_name=incident.location or incident.name,
                update_time=self._parse_update_time(incident.last_update),
                incident_no=incident.incident_no,
                previous_status=previous_status,
                change_type=change_type,
            )
            statuses.append(status)

        return statuses

    def run_check(self) -> List[EmergencyStatus]:
        """Run a single check cycle"""
        print(f"\n{'='*60}")
        print(f"VIC Emergency Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # Fetch incidents
        print("Fetching incidents from API...")
        incidents = self.client.fetch_incidents()
        print(f"Retrieved {len(incidents)} incidents\n")

        if not incidents:
            print("No incidents found.")
            return []

        # Process incidents
        print("Processing incidents...")
        statuses = self.process_incidents(incidents)

        # Update tracker state
        self.tracker.update_state(incidents)

        return statuses

    def format_output(
        self, statuses: List[EmergencyStatus], format_type: Optional[str] = None
    ) -> str:
        """Format the output in the requested format"""
        fmt = format_type or Config.OUTPUT_FORMAT

        if fmt == "json":
            return self._format_json(statuses)
        elif fmt == "csv":
            return self._format_csv(statuses)
        else:
            return self._format_table(statuses)

    def _format_table(self, statuses: List[EmergencyStatus]) -> str:
        """Format as ASCII table"""
        if not statuses:
            return "No active emergencies."

        # Sort by postcode
        sorted_statuses = sorted(statuses, key=lambda s: s.postcode)

        headers = ["Postcode", "Type", "Location Name", "Update Time", "Change"]
        rows = [
            [
                s.postcode,
                s.type[:50] + "..." if len(s.type) > 50 else s.type,
                s.location_name[:40] + "..." if len(s.location_name) > 40 else s.location_name,
                s.update_time.strftime("%Y-%m-%d %H:%M"),
                s.change_type.value if s.change_type != ChangeType.NONE else "",
            ]
            for s in sorted_statuses
        ]

        return tabulate(rows, headers=headers, tablefmt="grid")

    def _format_json(self, statuses: List[EmergencyStatus]) -> str:
        """Format as JSON"""
        return json.dumps(
            [s.to_dict() for s in statuses],
            indent=2,
            default=str,
        )

    def _format_csv(self, statuses: List[EmergencyStatus]) -> str:
        """Format as CSV"""
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["Postcode", "Type", "Location Name", "Update Time", "Change"],
        )
        writer.writeheader()
        for s in statuses:
            writer.writerow(s.to_dict())
        return output.getvalue()

    def get_changes_only(
        self, statuses: List[EmergencyStatus]
    ) -> List[EmergencyStatus]:
        """Filter to only statuses with changes"""
        return [
            s for s in statuses if s.change_type != ChangeType.NONE
        ]

    def close(self):
        """Clean up resources"""
        self.client.close()
