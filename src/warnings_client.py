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
        """Fetch ALL current incidents and warnings (not just formal warnings)"""
        try:
            response = self.session.get(self.TEXT_ONLY_URL, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            warnings = []

            # Find ALL incident/warning rows - not just class="warning"
            # The text-only page has different classes for different incident types
            # Look for all table rows that have incident data (data-href attribute or links)
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    # Skip header rows and empty rows
                    if row.find("th"):
                        continue
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue
                    # Check if this row has incident data (has a link in first cell)
                    first_cell = cells[0]
                    if first_cell.find("a"):
                        try:
                            warning = self._parse_warning_row(row)
                            if warning:
                                warnings.append(warning)
                        except Exception as e:
                            print(f"Error parsing row: {e}")
                            continue

            return warnings

        except requests.RequestException as e:
            print(f"Error fetching warnings: {e}")
            return []

    def _parse_warning_row(self, row) -> Optional[Warning]:
        """Parse a warning/incident table row - handles various row structures"""
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        # Get warning ID from data-href or generate from content
        warning_id = row.get("data-href", "").replace("#/warning/", "").replace("#/incident/", "")

        # Parse type cell (first cell with a link)
        type_cell = cells[0]
        link = type_cell.find("a")
        if not link:
            return None

        type_text = link.get_text(strip=True)
        url = link.get("href", "")

        # Generate ID if not found
        if not warning_id:
            warning_id = url.split("/")[-1] if "/" in url else type_text[:20]

        # Parse warning level, category, and condition
        warning_level, category, condition = self._parse_type(type_text)

        # Parse status (second cell) - handle various formats
        status = cells[1].get_text(strip=True) if len(cells) > 1 else "Unknown"

        # Parse location - try span.lastLocation first, then just text content
        location = ""
        if len(cells) > 2:
            location_span = cells[2].find("span", class_="lastLocation")
            if location_span:
                location = location_span.get_text(strip=True)
            else:
                location = cells[2].get_text(strip=True)
        suburbs = self._parse_suburbs(location)

        # Parse last updated - try span.lastUpdated, or look in later cells
        last_updated = datetime.now()
        for cell in cells[3:] if len(cells) > 3 else []:
            updated_span = cell.find("span", class_="lastUpdated")
            if updated_span:
                try:
                    timestamp_ms = int(updated_span.get_text(strip=True))
                    last_updated = datetime.fromtimestamp(timestamp_ms / 1000)
                    break
                except (ValueError, TypeError):
                    pass

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
            url=f"https://emergency.vic.gov.au{url}" if url and not url.startswith("http") else url,
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
