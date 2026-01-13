#!/usr/bin/env python3
"""
VIC Emergency Monitor

Monitors Victorian emergency incidents and reports status by postcode.
Can run as a one-off check or continuously with scheduled hourly polling.

Usage:
    python main.py              # Run once
    python main.py --schedule   # Run continuously (hourly)
    python main.py --json       # Output as JSON
    python main.py --csv        # Output as CSV
    python main.py --changes    # Show only status changes
"""

import argparse
import signal
import sys
import time
from datetime import datetime

import schedule

from src.monitor import VicEmergencyMonitor
from src.config import Config


def parse_args():
    parser = argparse.ArgumentParser(
        description="Monitor VIC Emergency incidents by postcode"
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run continuously with hourly polling",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=Config.POLL_INTERVAL,
        help=f"Polling interval in seconds (default: {Config.POLL_INTERVAL})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output in CSV format",
    )
    parser.add_argument(
        "--changes",
        action="store_true",
        help="Show only status changes (new, upgraded, downgraded, resolved)",
    )
    return parser.parse_args()


def run_check(monitor: VicEmergencyMonitor, args) -> None:
    """Run a single check and display results"""
    try:
        statuses = monitor.run_check()

        if args.changes:
            statuses = monitor.get_changes_only(statuses)
            if not statuses:
                print("No status changes detected since last check.")
                return

        # Determine output format
        if args.json:
            fmt = "json"
        elif args.csv:
            fmt = "csv"
        else:
            fmt = "table"

        output = monitor.format_output(statuses, fmt)
        print(output)

        # Summary
        if not args.json and not args.csv:
            print(f"\nTotal incidents: {len(statuses)}")
            changes = monitor.get_changes_only(statuses)
            if changes:
                print(f"Status changes: {len(changes)}")
                for c in changes:
                    print(f"  - {c.change_type.value}: {c.location_name} ({c.postcode})")

    except Exception as e:
        print(f"Error during check: {e}", file=sys.stderr)


def main():
    args = parse_args()
    monitor = VicEmergencyMonitor()

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down...")
        monitor.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.schedule:
        print(f"Starting VIC Emergency Monitor (polling every {args.interval} seconds)")
        print("Press Ctrl+C to stop\n")

        # Run immediately on start
        run_check(monitor, args)

        # Schedule subsequent runs
        schedule.every(args.interval).seconds.do(run_check, monitor, args)

        while True:
            schedule.run_pending()
            time.sleep(1)
    else:
        # Single run
        run_check(monitor, args)
        monitor.close()


if __name__ == "__main__":
    main()
