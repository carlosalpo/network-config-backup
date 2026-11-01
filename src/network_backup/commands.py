"""Platform profiles and conservative consultation-only CLI policy."""

import hashlib
import re

from .model import MAX_COMMANDS, Job

COMMON = {
    "Configuration": ["show running-config"],
    "Interfaces": ["show interfaces"],
    "Version & inventory": ["show version", "show inventory"],
    "Neighbors": ["show cdp neighbors detail", "show lldp neighbors detail"],
}
PROFILES = {
    p: {**COMMON, "Routing": ["show route" if p == "cisco_xr" else "show ip route"]}
    for p in ("cisco_ios", "cisco_xe", "cisco_xr", "cisco_nxos")
}
ROOTS = {
    "running-config",
    "startup-config",
    "interfaces",
    "interface",
    "version",
    "inventory",
    "ip",
    "ipv6",
    "route",
    "bgp",
    "ospf",
    "isis",
    "cdp",
    "lldp",
    "vlan",
    "vpc",
    "port-channel",
    "spanning-tree",
    "etherchannel",
    "vrf",
    "environment",
    "platform",
}
# Explicitly exclude shell syntax, CLI output redirection, help probes and session controls.
TOKENS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,239}\Z")
FORBIDDEN = {
    "redirect",
    "append",
    "delete",
    "erase",
    "reload",
    "install",
    "bash",
    "shell",
    "run",
    "clear",
    "debug",
    "copy",
    "write",
    "configure",
    "tech-support",
}


def validate_command(command):
    if not isinstance(command, str) or not TOKENS.fullmatch(command):
        raise ValueError(
            "Use one plain show query; pipes, control characters and chaining are blocked."
        )
    words = command.split()
    if len(words) < 2 or words[0].lower() != "show" or words[1].lower() not in ROOTS:
        raise ValueError("This show family is outside the consultation-only command policy.")
    if any(word.lower() in FORBIDDEN for word in words):
        raise ValueError("This query contains a blocked operation.")
    return " ".join(words)


def select_commands(platform, profiles, custom):
    selected = []
    for name in profiles:
        if name not in PROFILES[platform]:
            raise ValueError("Unknown collection profile.")
        selected.extend(
            (command, "configuration" if name == "Configuration" else "diagnostics")
            for command in PROFILES[platform][name]
        )
    selected.extend(
        (
            validate_command(line.strip()),
            "configuration"
            if line.strip().lower() in {"show running-config", "show startup-config"}
            else "diagnostics",
        )
        for line in custom.splitlines()
        if line.strip()
    )
    unique = {}
    for command, category in selected:
        command = validate_command(command)
        unique.setdefault(command.lower(), (command, category))
    if not 1 <= len(unique) <= MAX_COMMANDS:
        raise ValueError(f"Select 1–{MAX_COMMANDS} queries per device.")
    return list(unique.values())


def make_jobs(devices, selections):
    jobs = []
    for device in devices:
        selected = selections.get(device.name, [])
        if not 1 <= len(selected) <= MAX_COMMANDS:
            raise ValueError("Every device needs 1–50 selected queries.")
        seen = set()
        for command, category in selected:
            command = validate_command(command)
            if command.lower() in seen:
                raise ValueError("Duplicate query for a device.")
            seen.add(command.lower())
            if category not in {"configuration", "diagnostics"}:
                raise ValueError("Invalid collection category.")
            suffix = hashlib.sha256(command.lower().encode()).hexdigest()[:12]
            jobs.append(Job(f"{device.name}-{suffix}", device, command, category))
    return jobs
