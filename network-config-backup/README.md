# network-config-backup

Let's learn Network Automation by solving a networking problem we already understand.

This first version backs up running configurations from Cisco network devices using Python and Netmiko. It is intentionally small. The goal is not to build an enterprise backup platform. The goal is to see how a useful automation workflow is built, step by step, with tools that are approachable for network engineers.

## What Problem Are We Solving?

Network engineers often need a current copy of device configurations before a change, after a change, during troubleshooting, or as part of normal operational hygiene.

Manually, that usually looks like this:

```text
SSH -> Login -> show running-config -> Copy -> Save
```

That works for one router or switch. It becomes slow and error-prone when you need to repeat it across many devices.

With automation, we keep the same network task but let Python handle the repetition:

```text
inventory.yaml -> Python -> Netmiko -> Network Devices -> backups/
```

## What You Will Learn

In this mini-lab you will work with:

- Python basics
- YAML files
- SSH automation
- Device inventories
- Credential handling with environment variables
- Exception handling
- Working with network devices programmatically

## Project Structure

```text
network-config-backup/
├── README.md
├── backup.py
├── inventory.example.yaml
├── requirements.txt
├── .gitignore
└── backups/
    └── .gitkeep
```

## Requirements

- Python 3
- SSH access to Cisco IOS, IOS-XE, or NX-OS devices
- A user account that can run `show running-config`

This lab uses:

- Netmiko
- PyYAML

## Installation

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Inventory

Copy the example inventory:

```bash
cp inventory.example.yaml inventory.yaml
```

Edit `inventory.yaml` with your own lab devices:

```yaml
devices:
  - name: branch-router-01
    host: 192.0.2.10
    device_type: cisco_ios

  - name: access-switch-01
    host: 192.0.2.20
    device_type: cisco_ios

  - name: dc-core-01
    host: 192.0.2.30
    device_type: cisco_nxos
```

For Cisco IOS and IOS-XE, use:

```yaml
device_type: cisco_ios
```

For Cisco NX-OS, use:

```yaml
device_type: cisco_nxos
```

The real `inventory.yaml` file is ignored by Git so you can keep lab-specific IP addresses and hostnames out of the public repository.

## Credentials

Do not put usernames or passwords in the inventory file.

Set them as environment variables before running the script:

```bash
export NETWORK_USERNAME="your_username"
export NETWORK_PASSWORD="your_password"
```

If your devices require enable mode before showing the running configuration, you can also set:

```bash
export NETWORK_ENABLE_SECRET="your_enable_secret"
```

## Running the Backup

From this directory, run:

```bash
python backup.py
```

The script will:

1. Read devices from `inventory.yaml`.
2. Read credentials from environment variables.
3. SSH to each device using Netmiko.
4. Run `show running-config`.
5. Save each configuration under `backups/`.
6. Continue to the next device if one device fails.
7. Print a short summary at the end.

## Example Output

```text
Starting configuration backup for 3 device(s).

[branch-router-01] Connecting to 192.0.2.10...
[branch-router-01] Backup saved to backups/branch-router-01_20260818-141522.cfg

[access-switch-01] Connecting to 192.0.2.20...
[access-switch-01] Backup saved to backups/access-switch-01_20260818-141530.cfg

[dc-core-01] Connecting to 192.0.2.30...
[dc-core-01] Backup failed: Authentication failed.

Backup summary
Successful backups: 2
Failed backups:     1
```

## Security Considerations

- Never commit passwords to Git.
- Keep real inventories out of public repositories when they contain sensitive hostnames, IP addresses, or site details.
- Use a dedicated read-only or least-privilege account when possible.
- Protect any generated backup files because running configurations may contain SNMP communities, local users, keys, routing details, or other sensitive information.
- Consider storing production credentials in a secrets manager as your automation maturity grows.

## Where We Go From Here

This repository starts small on purpose. Future versions can build on the same idea:

- v1 - Basic configuration backup
- v2 - Better inventory and multiple platforms
- v3 - Logging and error handling improvements
- v4 - Configuration change detection
- v5 - Git configuration history
- v6 - NETCONF / model-driven programmability

The important part is the mindset: start with a real networking workflow, automate one useful step, understand it, and then improve it.
