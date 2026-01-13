"""
VIC Emergency Warnings Client - Scrapes warnings from the text-only page
"""

import re
import requests
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
from bs4 import BeautifulSoup


@dataclass
class Warning:
    """Warning from VIC Emergency"""
    warning_id: str
    type: str  # "Watch and Act - Fire - Monitor Conditions"
    warning_level: str  # "Watch and Act", "Advice", "Emergency Warning"
    category: str  # "Fire", "Flood", etc.
    condition: str  # "Monitor Conditions", "Not Safe to Return", etc.
    status: str  # "Moderate", "Minor", "Unknown"
    location: str  # List of affected areas
    suburbs: List[str]  # Parsed list of suburbs
    last_updated: datetime
    url: str


class WarningsClient:
    """Client to fetch warnings from VIC Emergency text-only page"""

    TEXT_ONLY_URL = "https://emergency.vic.gov.au/public/textonly.html"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "VicEmergencyMonitor/1.0",
            "Accept": "text/html",
            "Accept-Encoding": "gzip, deflate",
        })

    def fetch_warnings(self) -> List[Warning]:
        """Fetch all current warnings"""
        try:
            response = self.session.get(self.TEXT_ONLY_URL, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            warnings = []

            # Find all warning rows
            rows = soup.find_all("tr", class_="warning")

            for row in rows:
                try:
                    warning = self._parse_warning_row(row)
                    if warning:
                        warnings.append(warning)
                except Exception as e:
                    print(f"Error parsing warning row: {e}")
                    continue

            return warnings

        except requests.RequestException as e:
            print(f"Error fetching warnings: {e}")
            return []

    def _parse_warning_row(self, row) -> Optional[Warning]:
        """Parse a warning table row"""
        cells = row.find_all("td")
        if len(cells) < 4:
            return None

        # Get warning ID from data-href
        warning_id = row.get("data-href", "").replace("#/warning/", "")

        # Parse type cell
        type_cell = cells[0]
        link = type_cell.find("a")
        if not link:
            return None

        type_text = link.get_text(strip=True)
        url = link.get("href", "")

        # Parse warning level, category, and condition
        warning_level, category, condition = self._parse_type(type_text)

        # Parse status (Moderate, Minor, etc.)
        status = cells[1].get_text(strip=True)

        # Parse location
        location_span = cells[2].find("span", class_="lastLocation")
        location = location_span.get_text(strip=True) if location_span else ""
        suburbs = self._parse_suburbs(location)

        # Parse last updated
        updated_span = cells[3].find("span", class_="lastUpdated")
        if updated_span:
            timestamp_ms = int(updated_span.get_text(strip=True))
            last_updated = datetime.fromtimestamp(timestamp_ms / 1000)
        else:
            last_updated = datetime.now()

        return Warning(
            warning_id=warning_id,
            type=type_text,
            warning_level=warning_level,
            category=category,
            condition=condition,
            status=status,
            location=location,
            suburbs=suburbs,
            last_updated=last_updated,
            url=f"https://emergency.vic.gov.au{url}" if url else "",
        )

    def _parse_type(self, type_text: str) -> tuple:
        """Parse warning type into level, category, condition"""
        # Format: "Watch and Act - Fire - Monitor Conditions As They Are Changing"
        parts = [p.strip() for p in type_text.split(" - ")]

        warning_level = parts[0] if len(parts) > 0 else "Unknown"
        category = parts[1] if len(parts) > 1 else "Unknown"
        condition = " - ".join(parts[2:]) if len(parts) > 2 else ""

        return warning_level, category, condition

    def _parse_suburbs(self, location: str) -> List[str]:
        """Parse location string into list of suburbs"""
        if not location:
            return []

        # Split by comma and "and"
        parts = re.split(r",\s*|\s+and\s+", location)
        suburbs = [p.strip() for p in parts if p.strip()]

        # Remove "surrounds" and similar
        suburbs = [s for s in suburbs if s.lower() not in ["surrounds", "surrounding areas"]]

        return suburbs

    def close(self):
        self.session.close()
