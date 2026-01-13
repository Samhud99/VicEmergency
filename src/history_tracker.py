"""
History Tracker - Stores snapshots of warning data for comparison
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .config import Config


class HistoryTracker:
    """Tracks historical warning data for comparison"""

    def __init__(self, history_file: Optional[Path] = None):
        self.history_file = history_file or Config.DATA_DIR / "warning_history.json"
        self._history: Dict[str, List[dict]] = {}  # postcode -> list of snapshots
        self._snapshots: List[dict] = []  # list of full snapshots with timestamps
        self._load_history()

    def _load_history(self) -> None:
        """Load history from file"""
        Config.ensure_data_dir()
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    data = json.load(f)
                    self._history = data.get("by_postcode", {})
                    self._snapshots = data.get("snapshots", [])
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load history file: {e}")
                self._history = {}
                self._snapshots = []

    def _save_history(self) -> None:
        """Save history to file"""
        Config.ensure_data_dir()
        # Keep only last 100 snapshots to avoid file bloat
        if len(self._snapshots) > 100:
            self._snapshots = self._snapshots[-100:]

        with open(self.history_file, "w") as f:
            json.dump({
                "by_postcode": self._history,
                "snapshots": self._snapshots,
                "last_updated": datetime.now().isoformat(),
            }, f, indent=2, default=str)

    def save_snapshot(self, warnings: List[dict]) -> str:
        """Save a snapshot of current warnings, return snapshot ID"""
        timestamp = datetime.now()
        snapshot_id = timestamp.strftime("%Y%m%d_%H%M%S")

        # Create snapshot
        snapshot = {
            "id": snapshot_id,
            "timestamp": timestamp.isoformat(),
            "warnings": warnings,
            "postcode_summary": {}
        }

        # Update per-postcode history
        for warning in warnings:
            postcode = warning.get("Postcode", "Unknown")
            status = warning.get("Status", "Unknown")
            severity = warning.get("Severity", "Unknown")
            location = warning.get("Location", "")
            category = warning.get("HighLevelCategory", "")

            # Add to postcode summary
            snapshot["postcode_summary"][postcode] = {
                "status": status,
                "severity": severity,
                "location": location,
                "category": category,
            }

            # Add to per-postcode history
            if postcode not in self._history:
                self._history[postcode] = []

            # Add entry with timestamp
            entry = {
                "timestamp": timestamp.isoformat(),
                "status": status,
                "severity": severity,
                "location": location,
                "category": category,
                "type": warning.get("Type", ""),
            }

            # Only add if different from last entry
            if self._history[postcode]:
                last = self._history[postcode][-1]
                if last.get("status") != status or last.get("severity") != severity:
                    self._history[postcode].append(entry)
            else:
                self._history[postcode].append(entry)

            # Keep only last 50 entries per postcode
            if len(self._history[postcode]) > 50:
                self._history[postcode] = self._history[postcode][-50:]

        self._snapshots.append(snapshot)
        self._save_history()

        return snapshot_id

    def get_snapshots(self) -> List[dict]:
        """Get list of all snapshots with basic info"""
        return [
            {
                "id": s["id"],
                "timestamp": s["timestamp"],
                "warning_count": len(s.get("warnings", [])),
            }
            for s in self._snapshots
        ]

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Get a specific snapshot by ID"""
        for s in self._snapshots:
            if s["id"] == snapshot_id:
                return s
        return None

    def get_postcode_history(self, postcode: str) -> List[dict]:
        """Get history for a specific postcode"""
        return self._history.get(postcode, [])

    def compare_snapshots(
        self, snapshot_id_start: str, snapshot_id_end: str
    ) -> List[dict]:
        """Compare two snapshots and return changes by postcode"""
        start = self.get_snapshot(snapshot_id_start)
        end = self.get_snapshot(snapshot_id_end)

        if not start or not end:
            return []

        start_postcodes = start.get("postcode_summary", {})
        end_postcodes = end.get("postcode_summary", {})

        changes = []
        all_postcodes = set(start_postcodes.keys()) | set(end_postcodes.keys())

        for postcode in all_postcodes:
            start_data = start_postcodes.get(postcode)
            end_data = end_postcodes.get(postcode)

            if not start_data and end_data:
                # New warning
                changes.append({
                    "Postcode": postcode,
                    "Suburb": end_data.get("location", ""),
                    "Status Start": "No Warning",
                    "Status End": end_data.get("status", ""),
                    "Change": "NEW",
                })
            elif start_data and not end_data:
                # Warning removed
                changes.append({
                    "Postcode": postcode,
                    "Suburb": start_data.get("location", ""),
                    "Status Start": start_data.get("status", ""),
                    "Status End": "No Warning",
                    "Change": "RESOLVED",
                })
            elif start_data and end_data:
                start_status = start_data.get("status", "")
                end_status = end_data.get("status", "")

                if start_status != end_status:
                    change = self._determine_change(start_status, end_status)
                    changes.append({
                        "Postcode": postcode,
                        "Suburb": end_data.get("location", ""),
                        "Status Start": start_status,
                        "Status End": end_status,
                        "Change": change,
                    })

        return sorted(changes, key=lambda x: x["Postcode"])

    def _determine_change(self, start: str, end: str) -> str:
        """Determine if status increased, decreased, or remained"""
        severity_order = {
            "GOING": 1,
            "RESPONDING": 2,
            "CONTAINED": 3,
            "CONTROLLED": 4,
            "SAFE": 5,
            "No Warning": 6,
        }

        start_val = severity_order.get(start.upper(), 3)
        end_val = severity_order.get(end.upper(), 3)

        if end_val < start_val:
            return "INCREASED"
        elif end_val > start_val:
            return "DECREASED"
        else:
            return "REMAINED"

    def get_latest_snapshot_id(self) -> Optional[str]:
        """Get the most recent snapshot ID"""
        if self._snapshots:
            return self._snapshots[-1]["id"]
        return None
