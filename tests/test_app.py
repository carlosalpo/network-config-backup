import asyncio
import json
from pathlib import Path

from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static, TextArea

from network_backup.app import BackupApp


async def press(app, pilot, selector):
    widget = app.query_one(selector, Button)
    widget.scroll_visible(animate=False)
    await pilot.pause()
    assert await pilot.click(selector)
    await pilot.pause(0.35)  # Textual buttons suppress repeated clicks during their active effect.


async def ready(app, pilot):
    await pilot.press("ctrl+n")
    assert app.step == 1
    app.query_one("#credential-mode", Select).value = "all"
    await pilot.pause()
    await press(app, pilot, "#save-profile")
    assert len(app.assignments) == 4
    await pilot.press("ctrl+n")
    assert app.step == 2
    app.query_one("#custom", TextArea).load_text("show interfaces detailx")
    await press(app, pilot, "#apply-commands")
    assert len(app.selections) == 4


async def wait_finished(app, pilot):
    for _ in range(100):
        await pilot.pause()
        if not app.running:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Worker did not finish")


async def test_actual_wizard_retry_and_partial_export(tmp_path):
    app = BackupApp(demo=True)
    async with app.run_test(size=(150, 52)) as pilot:
        await pilot.pause()
        await ready(app, pilot)
        await press(app, pilot, "#collect")
        await wait_finished(app, pilot)
        assert app.step == 3
        results = list(app.collection.results.values())
        assert sum(r.status == "passed" for r in results) == 15
        assert sum(r.status == "invalid_command" for r in results) == 4
        invalid = next(r for r in results if r.status == "invalid_command")
        table = app.query_one("#results-table", DataTable)
        table.move_cursor(row=results.index(invalid))
        await pilot.pause()
        app.query_one("#replacement", Input).value = "show interfaces detail"
        passed_timestamps = {r.job.id: r.captured_at for r in results if r.status == "passed"}
        await press(app, pilot, "#retry")
        await wait_finished(app, pilot)
        assert invalid.status == "passed"
        assert all(
            app.collection.results[k].captured_at == value for k, value in passed_timestamps.items()
        )
        failed = next(r for r in results if r.status == "permission_denied")
        table.move_cursor(row=results.index(failed))
        await pilot.pause()
        app.query_one("#reason", Input).value = "Access review pending"
        await press(app, pilot, "#exclude")
        assert failed.status == "excluded"
        await pilot.press("ctrl+n")
        assert app.step == 4
        app.query_one("#destination", Input).value = str(tmp_path)
        await press(app, pilot, "#export")
        assert not list(tmp_path.iterdir())
        app.query_one("#sensitive-confirm", Checkbox).value = True
        await press(app, pilot, "#export")
        await wait_finished(app, pilot)
        assert app.saved_path
        report = json.loads((Path(app.saved_path) / "manifest.json").read_text())
        assert report["status"] == "partial"
        assert report["source"].startswith("synthetic-demo")
        assert "demo-only" not in json.dumps(report)


async def test_group_credentials_and_missing_profiles_block_continue():
    app = BackupApp(demo=True)
    async with app.run_test(size=(130, 48)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+n")
        await press(app, pilot, "#save-profile")
        assert len(app.assignments) == 2  # Campus
        await pilot.press("ctrl+n")
        assert app.step == 1
        for group in ["Datacenter", "WAN"]:
            app.query_one("#credential-scope", Select).value = group
            await pilot.pause()
            await press(app, pilot, "#save-profile")
        await pilot.press("ctrl+n")
        assert app.step == 2
        app.query_one("#command-scope", Select).value = "WAN|cisco_xr"
        await pilot.pause()
        await press(app, pilot, "#apply-commands")
        await press(app, pilot, "#collect")
        assert app.step == 2 and app.collection is None  # missing other scopes


async def test_compact_terminal_and_navigation_guards():
    app = BackupApp(demo=True)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        assert app.screen.has_class("narrow")
        await ready(app, pilot)
        await press(app, pilot, "#collect")
        await wait_finished(app, pilot)
        old = app.collection
        await pilot.press("ctrl+b")
        await press(app, pilot, "#collect")
        assert app.collection is old
        assert "Discard" in str(app.query_one("#status", Static).render())


async def test_no_inventory_no_connection_and_clear_validation():
    app = BackupApp()
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+n")
        assert app.step == 0 and app.devices == []
        app.query_one("#hosts", TextArea).load_text("192.0.2.10\n192.0.2.10")
        await press(app, pilot, "#load")
        assert app.devices == []
        assert "unique" in str(app.query_one("#status", Static).render())
