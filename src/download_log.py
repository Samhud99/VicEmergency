"""
Download Log - Tracks report downloads with user initials
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict

from .config import Config


@dataclass
class DownloadEntry:
    timestamp: str
    initials: str
    report_type: str
    filter_summary: str
    record_count: int


class DownloadLog:
    """Tracks report downloads"""

    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = log_file or Config.DATA_DIR / "download_log.json"
        self._entries: List[dict] = []
        self._load()

    def _load(self) -> None:
        Config.ensure_data_dir()
        if self.log_file.exists():
            try:
                with open(self.log_file) as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, KeyError):
                self._entries = []

    def _save(self) -> None:
        Config.ensure_data_dir()
        with open(self.log_file, "w") as f:
            json.dump(self._entries, f, indent=2)

    def add_entry(
        self,
        initials: str,
        report_type: str,
        filter_summary: str,
        record_count: int,
    ) -> DownloadEntry:
        """Add a download entry"""
        entry = DownloadEntry(
            timestamp=datetime.now().isoformat(),
            initials=initials.upper(),
            report_type=report_type,
            filter_summary=filter_summary,
            record_count=record_count,
        )
        self._entries.append(asdict(entry))
        # Keep only last 100 entries
        if len(self._entries) > 100:
            self._entries = self._entries[-100:]
        self._save()
        return entry

    def get_entries(self) -> List[dict]:
        """Get all download entries, most recent first"""
        return sorted(self._entries, key=lambda x: x["timestamp"], reverse=True)

    def get_timestamps(self) -> List[str]:
        """Get list of download timestamps for comparison selector"""
        return [e["timestamp"] for e in sorted(self._entries, key=lambda x: x["timestamp"], reverse=True)]
