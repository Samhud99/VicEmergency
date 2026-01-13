# VIC Emergency Monitor

Python application to monitor Victorian emergency incidents and provide postcode-based emergency status updates with change detection.

---

## API Source

**Endpoint:** `https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON`

**Source Update Frequency:** Every minute
**Default Polling:** Hourly (configurable)

---

## Output Schema

| Column | Type | Description |
|--------|------|-------------|
| `Postcode` | Text | Victorian postcode (3000-3999) |
| `Type` | Text | Format: `{IncidentStatus} - {Category2} - {OriginStatus}` |
| `Location Name` | Text | Suburb/location description |
| `Update Time` | DateTime | Last update timestamp |
| `Change` | Text | NEW, UPGRADE, DOWNGRADE, RESOLVED, or empty |

**Example:**
```
| Postcode | Type                                    | Location Name     | Update Time      | Change |
|----------|-----------------------------------------|-------------------|------------------|--------|
| 3156     | Responding - Medical - RESPONDING       | WANTIRNA SOUTH    | 2026-01-13 16:07 | NEW    |
| 3239     | Not Yet Under Control - Bushfire - GOING| CARLISLE RIVER    | 2026-01-12 15:20 |        |
| 3350     | Under Control - Bushfire - CONTROLLED   | BALLARAT          | 2026-01-13 14:35 | DOWN   |
```

---

## Status Change Detection

### Priority (Lower = More Severe)
```
RESPONDING/GOING (1) → CONTAINED (2) → CONTROLLED (3) → SAFE (4)
```

### Change Types
- **NEW**: Incident not seen before
- **UPGRADE**: Status escalated (e.g., CONTAINED → GOING)
- **DOWNGRADE**: Status de-escalated (e.g., GOING → CONTAINED)
- **RESOLVED**: Status changed to SAFE

---

## Usage

```bash
cd VicEmergency
source venv/bin/activate

# One-time check
python main.py

# Continuous hourly monitoring
python main.py --schedule

# Output formats
python main.py --json
python main.py --csv
python main.py --changes    # Only show status changes

# Custom interval (seconds)
python main.py --schedule --interval 1800
```

---

## Configuration (.env)

```env
POLL_INTERVAL=3600          # Seconds between checks
OUTPUT_FORMAT=table         # table, json, or csv
AZURE_MAPS_API_KEY=         # Optional: better geocoding
WEBHOOK_URL=                # Optional: POST alerts here
```

---

## Project Structure

```
VicEmergency/
├── main.py                 # CLI entry point
├── requirements.txt
├── .env
├── data/state.json         # Persisted state (auto-created)
└── src/
    ├── api_client.py       # API client
    ├── config.py           # Config loader
    ├── geocoder.py         # Postcode resolution
    ├── models.py           # Data models
    ├── monitor.py          # Main orchestrator
    └── status_tracker.py   # Change detection
```

---

## Sources
- [Emergency Data - EMV](https://www.emv.vic.gov.au/responsibilities/victorias-warning-system/emergency-data)
- [VicEmergency Data Feed Support](https://support.emergency.vic.gov.au/hc/en-gb/articles/235717508-How-do-I-access-the-VicEmergency-data-feed)
