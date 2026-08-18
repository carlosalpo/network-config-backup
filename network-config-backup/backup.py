from datetime import datetime
from pathlib import Path
import os
import re
import sys

import yaml
from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException


BASE_DIR = Path(__file__).resolve().parent
INVENTORY_FILE = BASE_DIR / "inventory.yaml"
BACKUP_DIR = BASE_DIR / "backups"


def load_inventory():
    if not INVENTORY_FILE.exists():
        print("inventory.yaml was not found. Copy inventory.example.yaml and edit it for your lab.")
        sys.exit(1)

    with INVENTORY_FILE.open("r", encoding="utf-8") as file:
        inventory = yaml.safe_load(file) or {}

    devices = inventory.get("devices", [])
    if not devices:
        print("No devices found in inventory.yaml.")
        sys.exit(1)

    return devices


def get_credentials():
    # I keep credentials outside the inventory so the device list can be committed
    # to Git without accidentally publishing passwords.
    username = os.getenv("NETWORK_USERNAME")
    password = os.getenv("NETWORK_PASSWORD")
    enable_secret = os.getenv("NETWORK_ENABLE_SECRET")

    if not username or not password:
        print("Set NETWORK_USERNAME and NETWORK_PASSWORD before running the backup.")
        sys.exit(1)

    return username, password, enable_secret


def safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def backup_device(device, username, password, enable_secret):
    name = device.get("name") or device.get("host")
    host = device.get("host")
    device_type = device.get("device_type")

    if not name or not host or not device_type:
        raise ValueError("Each device needs name, host, and device_type fields.")

    print(f"[{name}] Connecting to {host}...")

    connection_params = {
        "device_type": device_type,
        "host": host,
        "username": username,
        "password": password,
        "port": device.get("port", 22),
    }

    if enable_secret:
        connection_params["secret"] = enable_secret

    with ConnectHandler(**connection_params) as connection:
        if enable_secret:
            connection.enable()

        running_config = connection.send_command("show running-config")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{safe_filename(name)}_{timestamp}.cfg"
    backup_path = BACKUP_DIR / filename

    backup_path.write_text(running_config, encoding="utf-8")
    print(f"[{name}] Backup saved to {backup_path.relative_to(BASE_DIR)}")


def main():
    devices = load_inventory()
    username, password, enable_secret = get_credentials()

    BACKUP_DIR.mkdir(exist_ok=True)

    successful_backups = 0
    failed_backups = 0

    print(f"Starting configuration backup for {len(devices)} device(s).\n")

    for device in devices:
        name = device.get("name") or device.get("host") or "unknown-device"

        # If one switch is unreachable, I do not want the entire backup job to stop.
        # Each device gets its own try/except block, like troubleshooting one node at a time.
        try:
            backup_device(device, username, password, enable_secret)
            successful_backups += 1
        except (NetmikoAuthenticationException, NetmikoTimeoutException, OSError, ValueError) as error:
            failed_backups += 1
            print(f"[{name}] Backup failed: {error}")
        except Exception as error:
            failed_backups += 1
            print(f"[{name}] Unexpected failure: {error}")

        print()

    print("Backup summary")
    print(f"Successful backups: {successful_backups}")
    print(f"Failed backups:     {failed_backups}")


if __name__ == "__main__":
    main()
