"""Validated input and explicit per-command collection state."""

import csv
import io
import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

PLATFORMS = {"cisco_ios": "IOS", "cisco_xe": "IOS XE", "cisco_xr": "IOS XR", "cisco_nxos": "NX-OS"}
MAX_DEVICES = 100
MAX_COMMANDS = 50
MAX_INPUT_BYTES = 1_000_000
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
HOST = re.compile(r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\Z")


def now():
    return datetime.now(timezone.utc).isoformat()


def slug(value, label):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValueError(f"{label}: use 1–64 letters, digits, dots, underscores or hyphens.")
    return value


@dataclass(frozen=True)
class Device:
    name: str
    host: str
    platform: str
    group: str = "default"
    site: str = "default"
    port: int = 22

    def __post_init__(self):
        slug(self.name, "Device name")
        slug(self.group, "Group")
        slug(self.site, "Site")
        if self.platform not in PLATFORMS:
            raise ValueError("Supported platforms: cisco_ios, cisco_xe, cisco_xr, cisco_nxos.")
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            if not HOST.fullmatch(self.host) or any(
                not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
                for part in self.host.split(".")
            ):
                raise ValueError("Host must be an IP address or DNS hostname.") from None
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("SSH port must be an integer between 1 and 65535.")


class UniqueLoader(yaml.SafeLoader):
    """Do not silently override repeated YAML fields."""


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in mapping:
            raise ValueError("Inventory contains a duplicate or invalid field.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_inventory(text, kind="yaml", default_platform="cisco_ios"):
    if len(text.encode()) > MAX_INPUT_BYTES:
        raise ValueError("Inventory is limited to 1 MB.")
    try:
        if kind == "csv":
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("CSV requires unique named columns.")
            rows = list(reader)
        elif kind == "txt":
            rows = [
                {"name": f"device-{i:03d}", "host": line.strip(), "device_type": default_platform}
                for i, line in enumerate(text.splitlines(), 1)
                if line.strip()
            ]
        else:
            data = yaml.load(text, Loader=UniqueLoader)
            if not isinstance(data, dict) or set(data) != {"devices"}:
                raise ValueError("YAML must contain only a devices list.")
            rows = data["devices"]
    except yaml.YAMLError:
        raise ValueError("Invalid YAML inventory; check its structure.") from None
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_DEVICES:
        raise ValueError(f"Provide between 1 and {MAX_DEVICES} devices.")
    devices = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {
            "name",
            "host",
            "device_type",
            "platform",
            "group",
            "site",
            "port",
        }:
            raise ValueError("Unknown inventory fields; credentials do not belong in this file.")
        if row.get("device_type") and row.get("platform"):
            raise ValueError("Use either device_type or platform, not both.")
        try:
            if isinstance(row.get("port"), bool):
                raise ValueError
            port = int(row.get("port") or 22)
            if isinstance(row.get("port"), float):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("SSH port must be an integer.") from None
        device = Device(
            str(row.get("name") or ""),
            str(row.get("host") or "").lower(),
            str(row.get("device_type") or row.get("platform") or ""),
            str(row.get("group") or "default"),
            str(row.get("site") or "default"),
            port,
        )
        if any(
            d.name.casefold() == device.name.casefold()
            or (d.host, d.port) == (device.host, device.port)
            for d in devices
        ):
            raise ValueError("Device names and host/port pairs must be unique.")
        devices.append(device)
    return devices


def load_inventory(path):
    path = Path(path).expanduser()
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Choose an inventory file no larger than 1 MB.")
    kind = path.suffix.lower().lstrip(".")
    if kind not in {"csv", "yaml", "yml", "txt"}:
        raise ValueError("Choose a CSV, YAML or TXT inventory.")
    try:
        return parse_inventory(path.read_text(encoding="utf-8"), kind)
    except UnicodeError:
        raise ValueError("Inventory must be UTF-8 text.") from None


@dataclass(repr=False)
class Credential:
    username: str
    password: str = field(default="", repr=False)
    key_file: str = ""
    passphrase: str = field(default="", repr=False)
    secret: str = field(default="", repr=False)

    def validate(self):
        if not self.username.strip() or any(ord(c) < 32 for c in self.username):
            raise ValueError("Enter a username.")
        if bool(self.password) == bool(self.key_file):
            raise ValueError("Choose either a password or an SSH key file.")
        if self.key_file and not Path(self.key_file).expanduser().is_file():
            raise ValueError("SSH key file is not readable.")
        return self

    def __repr__(self):
        return "Credential(<private session data>)"


@dataclass(frozen=True)
class Job:
    id: str
    device: Device
    command: str
    category: str


@dataclass
class Result:
    job: Job
    status: str = "pending"
    message: str = "Not collected."
    output: str = field(default="", repr=False)
    captured_at: str | None = None
    attempts: list = field(default_factory=list)
    excluded_reason: str = ""

    def begin_attempt(self):
        if self.status == "passed":
            raise ValueError(
                "Passed captures are retained; start a new collection to refresh them."
            )
        if self.captured_at:
            self.attempts.append(
                {
                    "command": self.job.command,
                    "status": self.status,
                    "captured_at": self.captured_at,
                    "message": self.message,
                }
            )
        self.output = ""
        self.excluded_reason = ""

    def finish(self, status, message, output=""):
        self.status, self.message, self.output = status, message, output
        self.captured_at = now()
