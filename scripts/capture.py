"""Actual Textual screenshots of the explicit offline demo. No network or credentials."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

from textual.widgets import Button, DataTable, Input, Select, TextArea

from network_backup import __version__
from network_backup.app import BackupApp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/screenshots"


async def button(app, pilot, name):
    app.query_one("#" + name, Button).scroll_visible(animate=False)
    await pilot.pause()
    await pilot.click("#" + name)
    await pilot.pause(0.35)


def capture(app, name):
    # Screenshots are real widget renders; fixture timestamps are not live-lab evidence.
    (OUT / (name + ".svg")).write_text(
        app.export_screenshot(
            title="Network Configuration Backup · OFFLINE SYNTHETIC DEMO · no devices contacted"
        )
    )


async def main():
    # Capture the approved color theme; the actual CLI still honors NO_COLOR.
    os.environ.pop("NO_COLOR", None)
    OUT.mkdir(parents=True, exist_ok=True)
    app = BackupApp(demo=True)
    async with app.run_test(size=(150, 52)) as pilot:
        await pilot.pause()
        capture(app, "inventory")
        await pilot.press("ctrl+n")
        await pilot.pause()
        capture(app, "credentials")
        app.query_one("#credential-mode", Select).value = "all"
        await pilot.pause()
        await button(app, pilot, "save-profile")
        await pilot.press("ctrl+n")
        app.query_one("#custom", TextArea).load_text(
            "show ip interface brief\nshow interfaces detailx"
        )
        await button(app, pilot, "apply-commands")
        capture(app, "commands")
        await button(app, pilot, "collect")
        await app.workers.wait_for_complete()
        await pilot.pause()
        results = list(app.collection.results.values())
        selected = next(r for r in results if r.status == "invalid_command")
        app.query_one("#results-table", DataTable).move_cursor(row=results.index(selected))
        await pilot.pause()
        app.query_one("#replacement", Input).value = "show interfaces detail"
        capture(app, "review")
        await pilot.press("ctrl+n")
        await pilot.pause()
        capture(app, "save")
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        capture(app, "save-compact")
    manifest = {
        "version": __version__,
        "source": "Actual Textual export_screenshot using DemoTransport",
        "network": "No real device or network connection",
        "real_device_validation": "pending",
        "dimensions": "150x52 terminal cells; save-compact 80x30",
        "sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob("*.svg"))
        },
    }
    (OUT / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
