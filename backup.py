"""Compatibility entry point: environment credentials and the original YAML inventory."""

import os
import sys
from pathlib import Path

from network_backup.collector import Collection, NetmikoTransport
from network_backup.commands import make_jobs
from network_backup.export import export_collection
from network_backup.model import Credential, load_inventory

BASE_DIR = Path(__file__).resolve().parent
INVENTORY_FILE = BASE_DIR / "inventory.yaml"
BACKUP_DIR = BASE_DIR / "backups"


def main():
    try:
        devices = load_inventory(INVENTORY_FILE)
        credential = Credential(
            os.getenv("NETWORK_USERNAME", ""),
            os.getenv("NETWORK_PASSWORD", ""),
            secret=os.getenv("NETWORK_ENABLE_SECRET", ""),
        ).validate()
        transport = NetmikoTransport(os.getenv("NETWORK_KNOWN_HOSTS"))
        jobs = make_jobs(
            devices, {d.name: [("show running-config", "configuration")] for d in devices}
        )
        collection = Collection(jobs, transport)
        collection.collect({d.name: credential for d in devices})
        passed = sum(r.status == "passed" for r in collection.results.values())
        for r in collection.results.values():
            print(f"{r.job.device.name}: {r.status} — {r.message}")
        print(f"Successful backups: {passed}; failed: {len(jobs) - passed}")
        if passed:
            print(f"Saved to {export_collection(collection, BACKUP_DIR)}")
        return 0 if collection.complete else 1
    except (ValueError, OSError):
        print(
            "Check inventory.yaml, NETWORK_USERNAME, NETWORK_PASSWORD, verified SSH known_hosts and destination permissions."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
