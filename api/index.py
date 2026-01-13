# api/index.py
"""
Vercel Serverless Function - VIC Emergency Warnings API
Triggered by cron job every hour to fetch and return current warnings
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.warnings_client import WarningsClient


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Fetch current VIC Emergency warnings"""
        try:
            client = WarningsClient()
            warnings = client.fetch_warnings()
            client.close()

            # Convert to JSON-serializable format
            warnings_data = []
            for w in warnings:
                warnings_data.append({
                    "warning_id": w.warning_id,
                    "type": w.type,
                    "warning_level": w.warning_level,
                    "category": w.category,
                    "condition": w.condition,
                    "status": w.status,
                    "location": w.location,
                    "suburbs": w.suburbs,
                    "last_updated": w.last_updated.isoformat(),
                    "url": w.url,
                })

            response = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "count": len(warnings_data),
                "warnings": warnings_data,
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
