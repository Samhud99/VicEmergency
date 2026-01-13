import requests
from typing import List
from .models import Incident


API_URL = "https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON"


class VicEmergencyClient:
    """Client for the VIC Emergency API"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "VicEmergencyMonitor/1.0",
            "Accept": "application/json",
        })

    def fetch_incidents(self) -> List[Incident]:
        """Fetch all current incidents from the API"""
        try:
            response = self.session.get(API_URL, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            incidents = []

            for item in results:
                try:
                    incident = Incident.from_api_response(item)
                    # Only include incidents with valid coordinates (Victoria)
                    if incident.latitude != 0 and incident.longitude != 0:
                        incidents.append(incident)
                except Exception as e:
                    print(f"Warning: Failed to parse incident: {e}")
                    continue

            return incidents

        except requests.RequestException as e:
            print(f"Error fetching incidents: {e}")
            return []

    def close(self):
        self.session.close()
