import csv
import math
import time
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from .config import Config


class PostcodeDatabase:
    """Victorian postcode database with suburb and coordinate lookup"""

    def __init__(self):
        self._suburb_to_postcode: Dict[str, str] = {}
        self._postcode_coords: Dict[str, Tuple[float, float]] = {}
        self._all_coords: List[Tuple[str, float, float]] = []  # For nearest lookup
        self._load_database()

    def _load_database(self) -> None:
        """Load Victorian postcodes from CSV"""
        csv_path = Config.DATA_DIR / "vic_postcodes.csv"

        if not csv_path.exists():
            print(f"Warning: Postcode database not found at {csv_path}")
            return

        try:
            with open(csv_path, "r") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 4:
                        postcode, locality, lon_str, lat_str = row[:4]
                        try:
                            lat = float(lat_str)
                            lon = float(lon_str)
                        except ValueError:
                            continue

                        # Normalize locality name for matching
                        locality_upper = locality.strip().upper()

                        # Store suburb -> postcode mapping
                        if locality_upper not in self._suburb_to_postcode:
                            self._suburb_to_postcode[locality_upper] = postcode

                        # Store postcode coordinates (first occurrence)
                        if postcode not in self._postcode_coords:
                            self._postcode_coords[postcode] = (lat, lon)

                        # Store all coordinates for nearest lookup
                        self._all_coords.append((postcode, lat, lon))

            print(f"Loaded {len(self._suburb_to_postcode)} suburbs, {len(self._postcode_coords)} postcodes")

        except Exception as e:
            print(f"Error loading postcode database: {e}")

    def get_postcode_by_suburb(self, suburb: str) -> Optional[str]:
        """Look up postcode by suburb name"""
        if not suburb:
            return None
        suburb_upper = suburb.strip().upper()
        return self._suburb_to_postcode.get(suburb_upper)

    def get_nearest_postcode(self, lat: float, lon: float) -> Optional[str]:
        """Find nearest postcode by coordinates using Haversine distance"""
        if not self._all_coords or lat == 0 or lon == 0:
            return None

        min_distance = float("inf")
        nearest_postcode = None

        for postcode, plat, plon in self._all_coords:
            distance = self._haversine(lat, lon, plat, plon)
            if distance < min_distance:
                min_distance = distance
                nearest_postcode = postcode

        return nearest_postcode

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate Haversine distance between two points in km"""
        R = 6371  # Earth's radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        return R * c


class PostcodeGeocoder:
    """Resolves coordinates/locations to Australian postcodes"""

    def __init__(self):
        self.db = PostcodeDatabase()
        self.geolocator = Nominatim(user_agent="vic_emergency_monitor")
        self._geocode_cache: Dict[str, str] = {}
        self._last_request_time = 0
        self._min_delay = 1.1  # Nominatim requires 1 second between requests

    def _rate_limit(self):
        """Ensure we don't exceed Nominatim rate limits"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request_time = time.time()

    def _reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Get postcode via reverse geocoding API"""
        cache_key = f"{lat:.4f},{lon:.4f}"

        if cache_key in self._geocode_cache:
            return self._geocode_cache[cache_key]

        try:
            self._rate_limit()
            location = self.geolocator.reverse(
                f"{lat}, {lon}",
                exactly_one=True,
                language="en",
                addressdetails=True,
            )

            if location and location.raw.get("address"):
                postcode = location.raw["address"].get("postcode")
                if postcode:
                    self._geocode_cache[cache_key] = postcode
                    return postcode

        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"Geocoding error for ({lat}, {lon}): {e}")

        return None

    def resolve_postcode(
        self,
        location: str,
        latitude: float,
        longitude: float,
        municipality: str,
    ) -> str:
        """
        Resolve postcode using multiple strategies:
        1. Extract suburb from location string and look up
        2. Try municipality name
        3. Reverse geocode using coordinates
        4. Find nearest postcode by coordinates
        """
        # Strategy 1: Extract suburb from location and look up
        suburb = self._extract_suburb(location)
        if suburb:
            postcode = self.db.get_postcode_by_suburb(suburb)
            if postcode:
                return postcode

        # Strategy 2: Try municipality as suburb name
        if municipality:
            postcode = self.db.get_postcode_by_suburb(municipality)
            if postcode:
                return postcode

        # Strategy 3: Try to find postcode from incident name/location parts
        for part in self._extract_location_parts(location):
            postcode = self.db.get_postcode_by_suburb(part)
            if postcode:
                return postcode

        # Strategy 4: Reverse geocode (API call - rate limited)
        if latitude and longitude and latitude != 0 and longitude != 0:
            postcode = self._reverse_geocode(latitude, longitude)
            if postcode:
                return postcode

            # Strategy 5: Find nearest postcode by coordinates
            postcode = self.db.get_nearest_postcode(latitude, longitude)
            if postcode:
                return postcode

        # Fallback: return unknown
        return "Unknown"

    def _extract_suburb(self, location: str) -> Optional[str]:
        """Extract suburb name from location string"""
        if not location:
            return None

        # Common patterns:
        # "Street Name, SUBURB"
        # "X.XKM SW OF SUBURB"
        # "SUBURB"

        location = location.strip()

        # Pattern: "X.XKM [DIRECTION] OF SUBURB"
        distance_pattern = r"\d+\.?\d*\s*KM\s+[NSEW]+\s+OF\s+(.+)"
        match = re.search(distance_pattern, location, re.IGNORECASE)
        if match:
            return match.group(1).strip().upper()

        # Pattern: "Street, SUBURB" - take last part after comma
        if "," in location:
            parts = location.split(",")
            suburb = parts[-1].strip().upper()
            # Remove common suffixes
            suburb = re.sub(r"\s+(VIC|VICTORIA).*$", "", suburb, flags=re.IGNORECASE)
            if suburb:
                return suburb

        # If no comma, the whole thing might be a suburb
        return location.strip().upper()

    def _extract_location_parts(self, location: str) -> List[str]:
        """Extract all possible suburb names from location string"""
        if not location:
            return []

        parts = []
        location_upper = location.upper()

        # Split by common delimiters
        for delimiter in [",", " - ", "/", " AT ", " NEAR "]:
            for part in location_upper.split(delimiter):
                part = part.strip()
                # Remove distance prefixes
                part = re.sub(r"^\d+\.?\d*\s*KM\s+[NSEW]+\s+OF\s+", "", part)
                # Remove road/street suffixes for suburb extraction
                clean = re.sub(
                    r"\s+(ROAD|RD|STREET|ST|AVENUE|AVE|HIGHWAY|HWY|DRIVE|DR|LANE|LN|COURT|CT|PLACE|PL|CRESCENT|CR|BOULEVARD|BLVD)$",
                    "",
                    part,
                )
                if clean and len(clean) > 2:
                    parts.append(clean)

        return parts


# Convenience function for backward compatibility
def get_postcode_from_suburb(location: str) -> Optional[str]:
    """Quick suburb lookup without full geocoding"""
    db = PostcodeDatabase()
    geocoder = PostcodeGeocoder()
    suburb = geocoder._extract_suburb(location)
    if suburb:
        return db.get_postcode_by_suburb(suburb)
    return None


def extract_suburb_from_location(location: str) -> Optional[str]:
    """Extract suburb name from location string"""
    geocoder = PostcodeGeocoder()
    return geocoder._extract_suburb(location)
