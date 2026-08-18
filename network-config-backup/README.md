# Network Configuration Backup with Python

I wanted to put together a simple Network Automation example for network
engineers who are starting to experiment with Python.

There are many ways to start learning automation, but I think it is easier
when the first use case is something we already understand from the networking
side.

So I decided to start with configuration backups.

Most of us have done this manually many times:

```text
SSH -> Login -> show running-config -> Copy -> Save
```

There is nothing particularly complicated about that workflow. The problem is
that doing it manually does not scale very well.

This project takes that same workflow and lets Python handle the repetitive part:

```text
inventory.yaml -> Python -> Netmiko -> Network Devices -> backups/
```

That's really all this first version is intended to do.

It is not meant to replace a configuration management or backup platform. I'm
using it as a practical way to explore Python, Netmiko and Network Automation
with a use case that makes sense to a network engineer.

---

## What the script does

The script reads a list of devices from a YAML inventory, connects to each one
using SSH, retrieves the running configuration and saves it locally.

For now I am keeping the workflow intentionally simple:

1. Read the device inventory.
2. Get the credentials from environment variables.
3. Connect to the device with Netmiko.
4. Run `show running-config`.
5. Save the configuration with the device name and timestamp.
6. Move on to the next device if something fails.
7. Show a simple summary when the job finishes.

The first version supports Cisco IOS/IOS-XE and NX-OS.

---

## Why I started with Netmiko

I could have started this project with NETCONF, RESTCONF or APIs, but that adds
several concepts at the same time.

For a first exercise I wanted the automation to look very similar to what I
would normally do manually from the CLI.

Netmiko gives us a good bridge between those two worlds:

```text
What I normally do:

Laptop -> SSH -> Network Device -> CLI commands


What the script does:

Python -> Netmiko -> SSH -> Network Device -> CLI commands
```

Once that workflow is clear, moving into model-driven approaches such as
NETCONF becomes much easier to understand.

---

## Project structure

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

I keep the actual `inventory.yaml` and generated configuration backups outside
Git tracking because I don't want lab IP addresses, hostnames or device
configurations ending up in the public repository.

---

## Requirements

You will need:

- Python 3
- SSH connectivity to the network devices
- A user account with enough privileges to read the running configuration

The Python dependencies are intentionally minimal:

- Netmiko
- PyYAML

---

## Getting started

Clone the repository and move into the project directory.

I normally prefer using a Python virtual environment so the packages for this
project stay separate from everything else installed on the system.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Then install the dependencies:

```bash
pip install -r requirements.txt
```

---

## Create your inventory

Start by copying the example:

```bash
cp inventory.example.yaml inventory.yaml
```

Then add your own devices:

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

For IOS and IOS-XE I'm using:

```yaml
device_type: cisco_ios
```

For NX-OS:

```yaml
device_type: cisco_nxos
```

The `name` field is simply the name I want to use when creating the backup
file.

---

## Credentials

I don't store usernames or passwords inside the inventory.

Before running the script, set the credentials as environment variables:

```bash
export NETWORK_USERNAME="your_username"
export NETWORK_PASSWORD="your_password"
```

If the device requires an enable secret:

```bash
export NETWORK_ENABLE_SECRET="your_enable_secret"
```

Keeping credentials outside the code is a small detail, but it is an important
habit when we start putting automation projects into Git.

---

## Run the backup

Now run:

```bash
python backup.py
```

You should see something similar to:

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

One thing I wanted from the beginning was for a failed device not to stop the
entire job. If one router or switch cannot be reached, the script reports the
failure and continues with the rest of the inventory.

---

## A note about security

This is a lab project, but I still think it is worth building good habits from
the beginning.

A few things to keep in mind:

- Don't put passwords directly in the Python script.
- Don't commit real configuration backups to a public repository.
- Be careful with inventories containing production addressing or hostnames.
- Use a dedicated account with only the privileges the automation actually needs.
- Remember that running configurations can contain credentials, SNMP
  communities, routing information and other sensitive data.

For a larger environment I would not rely on environment variables alone. A
proper secrets management solution would make more sense.

But for this first lab, I want to keep the number of moving parts small.

---

## What am I actually learning here?

The interesting part of this project isn't really the configuration backup.

The backup is just the use case.

By building it we are already touching several concepts that become important
as we move deeper into Network Automation:

```text
YAML                  -> storing structured data
Python                -> automation logic
Netmiko               -> interacting with network devices
SSH                    -> device connectivity
Environment variables -> basic credential handling
Exceptions             -> dealing with failures
Git                    -> versioning the automation itself
```

That's the main reason I like starting with something simple like this.

We can concentrate on understanding the pieces instead of immediately hiding
everything behind a larger automation framework.

---

## Where I want to take this next

I plan to keep evolving the same project instead of jumping directly into a
much more complicated example.

Something along these lines:

```text
v1  Basic configuration backup
 |
 v2  Better inventory + additional platforms
 |
 v3  Structured logging + better error reporting
 |
 v4  Detect configuration changes
 |
 v5  Store configuration history in Git
 |
 v6  Rebuild the workflow using NETCONF
```

The last step is particularly interesting to me.

At that point we can compare the CLI-based approach we started with against a
model-driven approach and understand why technologies such as NETCONF and YANG
matter, instead of learning them only as abstract concepts.

For now, though, the objective is much simpler:

**Take one networking task you already understand and automate it.**

Then improve it one step at a time.
