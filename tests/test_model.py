from dataclasses import replace

import pytest

from network_backup.commands import make_jobs, select_commands, validate_command
from network_backup.model import Credential, Device, load_inventory, parse_inventory


def test_legacy_yaml_inventory():
    devices = load_inventory("inventory.example.yaml")
    assert len(devices) == 3
    assert devices[0].platform == "cisco_ios"


def test_csv_and_plain_hosts():
    devices = load_inventory("examples/devices.csv")
    assert {d.platform for d in devices} == {"cisco_ios", "cisco_xe", "cisco_xr", "cisco_nxos"}
    assert parse_inventory("192.0.2.1\nrouter.example", "txt")[1].host == "router.example"


@pytest.mark.parametrize(
    "text,kind",
    [
        ("devices: []", "yaml"),
        ("devices: [hello]", "yaml"),
        ("devices: [{name: a, host: 192.0.2.1, device_type: cisco_ios, password: secret}]", "yaml"),
        ("devices: [{name: ../escape, host: 192.0.2.1, device_type: cisco_ios}]", "yaml"),
        ("devices: [{name: a, host: 192.0.2.1, device_type: cisco_ios, port: true}]", "yaml"),
        ("devices: [{name: a, host: 192.0.2.1, device_type: cisco_ios, port: 22.9}]", "yaml"),
        ("devices: [{name: a, host: 192.0.2.1, device_type: unknown}]", "yaml"),
        ("devices: [{name: a, name: b}]", "yaml"),
        ("devices: [", "yaml"),
        ("name,host,host\na,192.0.2.1,192.0.2.2", "csv"),
        ("-oProxyCommand=touch /tmp/x", "txt"),
        ("hello\x1b[31m", "txt"),
        ("192.0.2.1\n192.0.2.1", "txt"),
        ("a..example", "txt"),
    ],
)
def test_inventory_rejects_invalid_or_secret_fields(text, kind):
    with pytest.raises(ValueError):
        parse_inventory(text, kind)


def test_inventory_limits_and_case_collisions():
    with pytest.raises(ValueError):
        parse_inventory("x" * 1_000_001, "txt")
    with pytest.raises(ValueError):
        parse_inventory("\n".join(f"192.0.2.{i}" for i in range(1, 102)), "txt")
    with pytest.raises(ValueError):
        parse_inventory(
            "name,host,device_type\nRouter,192.0.2.1,cisco_ios\nrouter,192.0.2.2,cisco_ios", "csv"
        )


@pytest.mark.parametrize(
    "command",
    [
        "show version;reload",
        "show version\nreload",
        "show running-config | redirect flash:x",
        "show tech-support",
        "configure terminal",
        "show version\x1b",
        "show ip route > file",
        "show platform shell",
        "show ?",
        "",
        "show version && reload",
        "show version\rreload",
        "show $(whoami)",
        "show `whoami`",
    ],
)
def test_command_policy(command):
    with pytest.raises(ValueError):
        validate_command(command)


@pytest.mark.parametrize("platform", ["cisco_ios", "cisco_xe", "cisco_xr", "cisco_nxos"])
def test_profiles_and_duplicate_custom_queries(platform):
    selected = select_commands(
        platform, ["Configuration", "Routing"], "show running-config\nshow interfaces"
    )
    assert len(selected) == 3
    assert selected[1][0] == ("show route" if platform == "cisco_xr" else "show ip route")
    device = Device("router", "192.0.2.1", platform)
    assert len(make_jobs([device], {"router": selected})) == 3


def test_job_requires_every_device_and_no_duplicate_queries():
    device = Device("r1", "192.0.2.1", "cisco_ios")
    with pytest.raises(ValueError):
        make_jobs([device], {})
    with pytest.raises(ValueError):
        make_jobs([device], {"r1": [("show version", "diagnostics")] * 2})
    with pytest.raises(ValueError):
        replace(device, port=65536)


def test_credentials_are_private_and_exclusive(tmp_path):
    key = tmp_path / "key"
    key.write_text("dummy")
    cred = Credential("reader", "private-password", secret="private-enable").validate()
    assert "private-password" not in repr(cred)
    assert "private-enable" not in repr(cred)
    for invalid in [
        Credential(""),
        Credential("reader", "x", str(key)),
        Credential("reader", key_file="/missing"),
    ]:
        with pytest.raises(ValueError):
            invalid.validate()
    assert Credential("reader", key_file=str(key)).validate()
