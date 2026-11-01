import importlib.util
from pathlib import Path

from network_backup.demo import DemoTransport


def test_original_entrypoint_and_environment_names(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("legacy", Path(__file__).parents[1] / "backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inventory = tmp_path / "inventory.yaml"
    inventory.write_text(
        "devices:\n  - name: example\n    host: 192.0.2.10\n    device_type: cisco_ios\n"
    )
    monkeypatch.setattr(module, "INVENTORY_FILE", inventory)
    monkeypatch.setattr(module, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(module, "NetmikoTransport", lambda _: DemoTransport())
    monkeypatch.setenv("NETWORK_USERNAME", "reader")
    monkeypatch.setenv("NETWORK_PASSWORD", "do-not-log")
    assert module.main() == 0
    assert list((tmp_path / "backups").glob("backup-*/manifest.json"))
    assert "do-not-log" not in capsys.readouterr().out
