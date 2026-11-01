import hashlib
import json
import os

import pytest
from netmiko.exceptions import NetmikoAuthenticationException, ReadTimeout

from network_backup.collector import Collection, NetmikoTransport, classify
from network_backup.commands import make_jobs
from network_backup.export import export_collection
from network_backup.model import Credential, Device


class Fake:
    def __init__(self, outputs=None, connect_error=None):
        self.outputs = outputs or {}
        self.connect_error = connect_error
        self.sent, self.closed, self.connections = [], 0, []

    def connect(self, device, credential):
        self.connections.append(device.name)
        if self.connect_error:
            raise self.connect_error
        return self

    def query(self, connection, command):
        self.sent.append(command)
        value = self.outputs.get(command, "Interface is up\nend")
        if isinstance(value, Exception):
            raise value
        return value

    def disconnect(self):
        self.closed += 1


def planned(fake=None, commands=None):
    d = Device("r1", "192.0.2.1", "cisco_ios")
    jobs = make_jobs(
        [d], {"r1": [(c, "diagnostics") for c in (commands or ["show interfaces", "show version"])]}
    )
    return Collection(jobs, fake or Fake()), {"r1": Credential("reader", "secret-123")}


@pytest.mark.parametrize(
    "output,status",
    [
        ("", "empty"),
        ("  \n", "empty"),
        ("% Invalid input detected at ^ marker.", "invalid_command"),
        ("% Incomplete command.", "invalid_command"),
        ("% Ambiguous command: show i", "invalid_command"),
        ("% Authorization failed.", "permission_denied"),
        ("Permission denied", "permission_denied"),
        ("Command authorization failed", "permission_denied"),
        ("Unknown command", "invalid_command"),
        ("abc\n--More--", "incomplete"),
        ("Output truncated", "incomplete"),
        ("% Error: query failed", "device_error"),
        ("description Invalid input is a test\ninterface GigabitEthernet0/0", "passed"),
    ],
)
def test_cli_results_are_not_just_successful_ssh(output, status):
    assert classify(output) == status


def test_connection_settings_and_no_implicit_enable(tmp_path):
    known = tmp_path / "known_hosts"
    known.write_text("fixture")
    captured = {}

    class Conn:
        def enable(self):
            captured["enabled"] = True

    def factory(**kwargs):
        captured.update(kwargs)
        return Conn()

    transport = NetmikoTransport(known, connector=factory)
    d = Device("r", "192.0.2.1", "cisco_ios")
    transport.connect(d, Credential("reader", "secret"))
    assert captured["ssh_strict"] is True
    assert captured["alt_key_file"] == str(known)
    assert captured["allow_agent"] is False
    assert captured["session_log"] is None
    assert captured["allow_auto_change"] is False
    assert "enabled" not in captured
    transport.connect(d, Credential("reader", "secret", secret="enable"))
    assert captured["enabled"] is True


def test_failed_query_can_be_edited_without_rerunning_passed():
    fake = Fake({"show interfaces": "% Invalid input detected"})
    run, creds = planned(fake)
    run.collect(creds)
    first, second = run.results.values()
    good_time = second.captured_at
    run.edit(first.job.id, "show interfaces detail")
    run.collect(creds, [first.job.id])
    assert fake.sent == ["show interfaces", "show version", "show interfaces detail"]
    assert second.captured_at == good_time
    assert first.attempts[0]["command"] == "show interfaces"
    assert run.complete and fake.closed == 2
    with pytest.raises(ValueError):
        run.edit(second.job.id, "show inventory")


def test_timed_out_session_is_not_reused():
    fake = Fake({"show interfaces": ReadTimeout("sensitive password here")})
    run, creds = planned(fake)
    run.collect(creds)
    assert fake.sent == ["show interfaces"] and fake.closed == 1
    assert [r.status for r in run.results.values()] == ["timeout", "session_failed"]
    assert "sensitive" not in repr(run.results)


def test_authentication_failure_once_per_device_and_safe_errors():
    fake = Fake(connect_error=NetmikoAuthenticationException("password=secret-123"))
    run, creds = planned(fake)
    run.collect(creds)
    assert fake.connections == ["r1"] and fake.sent == []
    assert all(r.status == "authentication_failed" for r in run.results.values())
    assert "secret-123" not in repr(run.results)


def test_exclusion_requires_reason_and_passed_cannot_be_discarded():
    fake = Fake({"show interfaces": "% Authorization failed"})
    run, creds = planned(fake)
    run.collect(creds)
    first, second = run.results.values()
    with pytest.raises(ValueError):
        run.exclude(first.job.id, "")
    run.exclude(first.job.id, "Access review pending")
    assert first.status == "excluded" and not run.complete
    with pytest.raises(ValueError):
        run.exclude(second.job.id, "discard")
    run.collect(creds)
    assert len(fake.sent) == 2


def test_cancellation_and_lock_reject_overlapping_work():
    run, creds = planned()

    def progress():
        run.cancel.set()
        with pytest.raises(ValueError):
            run.collect(creds)
        with pytest.raises(ValueError):
            run.edit(next(iter(run.results)), "show inventory")

    run.collect(creds, progress=progress)
    assert [r.status for r in run.results.values()] == ["passed", "cancelled"]


def test_size_limit_never_marks_passed(monkeypatch):
    monkeypatch.setattr("network_backup.collector.MAX_OUTPUT", 3)
    run, creds = planned()
    run.collect(creds)
    assert all(r.status == "output_limit" and not r.output for r in run.results.values())


def test_private_atomic_partial_export_and_integrity(tmp_path):
    fake = Fake({"show interfaces": "% Authorization failed"})
    run, creds = planned(fake)
    run.collect(creds)
    run.exclude(next(iter(run.results)), "<script>alert(1)</script>")
    path = export_collection(run, tmp_path)
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["status"] == "partial"
    assert len(manifest["queries"]) == 2
    assert manifest["queries"][0]["excluded_reason"] == "<script>alert(1)</script>"
    assert "<script>" not in (path / "summary.html").read_text()
    assert "secret-123" not in (path / "manifest.json").read_text()
    for line in (path / "SHA256SUMS").read_text().splitlines():
        digest, filename = line.split("  ", 1)
        assert hashlib.sha256((path / filename).read_bytes()).hexdigest() == digest
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o077 == 0 for p in path.rglob("*"))
    assert export_collection(run, tmp_path) != path


def test_empty_and_symlink_exports_rejected(tmp_path):
    run, creds = planned()
    with pytest.raises(ValueError):
        export_collection(run, tmp_path)
    run.collect(creds)
    link = tmp_path / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        export_collection(run, link)


def test_export_failure_does_not_create_completed_backup(tmp_path, monkeypatch):
    run, creds = planned()
    run.collect(creds)
    monkeypatch.setattr(
        "network_backup.export.private_write",
        lambda *args: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError, match="did not finish"):
        export_collection(run, tmp_path)
    assert not list(tmp_path.glob("backup-*"))
    assert list(tmp_path.glob(".ncb-incomplete-*"))


def test_cancel_before_worker_starts_never_connects():
    fake = Fake()
    run, creds = planned(fake)
    run.cancel.set()
    run.collect(creds)
    assert not fake.connections
    assert all(r.status == "cancelled" for r in run.results.values())


def test_export_holds_operation_lock(tmp_path, monkeypatch):
    from network_backup import export as exporter

    run, creds = planned()
    run.collect(creds)
    original = exporter.private_write

    def guarded(path, data):
        with pytest.raises(ValueError, match="already running"):
            run.collect(creds)
        return original(path, data)

    monkeypatch.setattr(exporter, "private_write", guarded)
    assert exporter.export_collection(run, tmp_path).is_dir()
    assert not run.busy
