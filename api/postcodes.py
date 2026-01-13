# api/postcodes.py
"""
Vercel Serverless Function - Warnings by Postcode
Returns current warnings grouped by postcode
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.warnings_client import WarningsClient
from src.geocoder import PostcodeGeocoder


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Fetch warnings grouped by postcode"""
        try:
            # Fetch warnings
            client = WarningsClient()
            warnings = client.fetch_warnings()
            client.close()

            # Initialize geocoder
            geocoder = PostcodeGeocoder()

            # Group by postcode
            postcode_warnings = {}
            for w in warnings:
                for suburb in w.suburbs:
                    pc = geocoder.db.get_postcode_by_suburb(suburb.upper())
                    if pc:
                        if pc not in postcode_warnings:
                            postcode_warnings[pc] = {
                                "postcode": pc,
                                "suburbs": [],
                                "warnings": [],
                                "highest_status": None,
                                "highest_level": None,
                            }

                        if suburb not in postcode_warnings[pc]["suburbs"]:
                            postcode_warnings[pc]["suburbs"].append(suburb)

                        # Track highest severity
                        status_order = {"Moderate": 1, "Minor": 2, "Unknown": 3}
                        level_order = {"Emergency Warning": 1, "Watch and Act": 2, "Advice": 3}

                        current_status = postcode_warnings[pc]["highest_status"]
                        if current_status is None or status_order.get(w.status, 4) < status_order.get(current_status, 4):
                            postcode_warnings[pc]["highest_status"] = w.status

                        current_level = postcode_warnings[pc]["highest_level"]
                        if current_level is None or level_order.get(w.warning_level, 4) < level_order.get(current_level, 4):
                            postcode_warnings[pc]["highest_level"] = w.warning_level

                        postcode_warnings[pc]["warnings"].append({
                            "warning_id": w.warning_id,
                            "type": w.type,
                            "status": w.status,
                            "warning_level": w.warning_level,
                            "last_updated": w.last_updated.isoformat(),
                        })

            # Sort by postcode
            sorted_postcodes = sorted(postcode_warnings.values(), key=lambda x: x["postcode"])

            response = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "count": len(sorted_postcodes),
                "postcodes": sorted_postcodes,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response, indent=2).encode("utf-8"))

        except Exception as e:
            error_response = {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode("utf-8"))

        return
