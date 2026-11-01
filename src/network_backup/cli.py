import argparse

from . import __version__


def main():
    parser = argparse.ArgumentParser(
        description="Guided SSH configuration and diagnostics collection."
    )
    parser.add_argument(
        "--version", action="version", version=f"Network Configuration Backup {__version__}"
    )
    parser.add_argument("--inventory", help="CSV, YAML or TXT inventory path (no passwords)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Offline synthetic demonstration; never connects to devices",
    )
    args = parser.parse_args()
    from .app import BackupApp

    BackupApp(args.inventory, args.demo).run()
