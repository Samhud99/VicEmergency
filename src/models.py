from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ChangeType(Enum):
    NEW = "NEW"
    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"
    RESOLVED = "RESOLVED"
    NONE = "NONE"


class StatusPriority(Enum):
    """Lower number = more severe/urgent"""
    GOING = 1
    RESPONDING = 1
    CONTAINED = 2
    CONTROLLED = 3
    SAFE = 4


@dataclass
class Incident:
    """Raw incident from the API"""
    incident_no: int
    incident_type: str
    category1: str
    category2: str
    name: str
    location: str
    municipality: str
    latitude: float
    longitude: float
    incident_status: str
    origin_status: str
    incident_size: str
    last_update: str
    resource_count: int
    territory: str

    @classmethod
    def from_api_response(cls, data: dict) -> "Incident":
        return cls(
            incident_no=data.get("incidentNo", 0),
            incident_type=data.get("incidentType", ""),
            category1=data.get("category1", ""),
            category2=data.get("category2", ""),
            name=data.get("name", ""),
            location=data.get("incidentLocation", ""),
            municipality=data.get("municipality", ""),
            latitude=float(data.get("latitude", 0) or 0),
            longitude=float(data.get("longitude", 0) or 0),
            incident_status=data.get("incidentStatus", ""),
            origin_status=data.get("originStatus", ""),
            incident_size=data.get("incidentSize", ""),
            last_update=data.get("lastUpdateDateTime", ""),
            resource_count=int(data.get("resourceCount", 0) or 0),
            territory=data.get("territory", ""),
        )


@dataclass
class EmergencyStatus:
    """Output schema as requested"""
    postcode: str
    type: str  # Format: "{IncidentStatus} - {Category2} - {OriginStatus}"
    location_name: str
    update_time: datetime
    incident_no: int
    previous_status: Optional[str] = None
    change_type: ChangeType = ChangeType.NONE

    def to_dict(self) -> dict:
        return {
            "Postcode": self.postcode,
            "Type": self.type,
            "Location Name": self.location_name,
            "Update Time": self.update_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Change": self.change_type.value if self.change_type != ChangeType.NONE else "",
        }
