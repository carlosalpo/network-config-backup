# Operations and security

## Scope

This preview collects existing configuration and operational CLI output. It never sends `configure terminal`, configuration edits, reload, erase, restore, `write memory` or `copy running-config startup-config`. Netmiko may send terminal/session setup queries such as disabling paging or setting terminal width. An explicitly supplied enable secret requests privilege elevation. These session operations do not constitute a network configuration deployment.

Profiles cover four declared Netmiko platforms. They are candidate queries, not a guarantee that every software release supports every command. Routing uses `show route` for IOS XR; it uses `show ip route` for IOS, IOS XE and NX-OS. The UI does not certify the detected OS. NETCONF is a future adapter, not a hidden fallback.

## Custom queries

Only single-line `show` queries in the following families are accepted:

`running-config`, `startup-config`, `interfaces`, `interface`, `version`, `inventory`, `ip`, `ipv6`, `route`, `bgp`, `ospf`, `isis`, `cdp`, `lldp`, `vlan`, `vpc`, `port-channel`, `spanning-tree`, `etherchannel`, `vrf`, `environment`, `platform`.

Shell characters, pipes (including output filters), redirection, newlines/chaining, help probes and explicitly blocked operation words are rejected. `show tech-support` is not supported in this first version. This conservative syntax policy is not a substitute for a device-side read-only AAA policy or an operator's review of expensive commands. No command is guaranteed harmless merely by its name.

The application matches known CLI error patterns, detects blank responses and some paging/truncation markers, and treats transport uncertainty as failure. Unknown device-specific error wording can evade classification. For representative devices, manually inspect outputs before relying on a recurring operational process.

## SSH identities and credentials

Prepare an SSH `known_hosts` file after checking fingerprints through an independently trusted source. Do not trust a scanned key simply because a scan returned it. The application uses Netmiko with strict host-key checking, no automatic enrollment, no SSH agent fallback, and no session logs. Nonstandard ports use the standard `[host]:port` known_hosts notation.

Profiles support password or SSH key authentication, optional key passphrase, and optional enable secret. Credentials are held in Python memory; this is not a secure-memory vault and cannot promise memory zeroization or protection from an administrator/process dump. The assistant does not serialize them in plans, manifests or error messages. It uses generic error messages instead of propagating exception content that may contain secrets.

Device configurations themselves may contain passwords, keys, communities or private addressing. Original successful command outputs are preserved, not silently redacted. Reports contain query metadata rather than raw configuration content. Free-text query and exclusion fields are operator-authored and are included in reports. Do not put credentials in them.

## Failure and storage behavior

A result is tracked per device/query; earlier attempts are preserved as metadata. Passed queries cannot be edited, excluded or retried in place. Start a new collection to refresh them. Changing access profiles does not rewrite older capture timestamps. Unknown or unreachable devices remain in a partial report.

After a query timeout or stream failure, remaining queries on that device are not sent. Retry explicitly, creating a fresh SSH session. Cancellation waits for the current bounded operation and preserves completed results. No automatic retry or repair is performed.

Successful output stays in process memory until export. A crash or unexported exit loses it; the UI asks for a second quit when captures are unsaved. There is no background disk spool or resume-after-restart in this version.

Export first writes to a unique private staging directory inside the destination, flushes each file and then renames the directory. This prevents an ordinary write failure from labeling a partial write as a finished backup. It is not a guarantee against hardware failure or power loss. Existing exports are never overwritten. A direct symlink destination is rejected. The destination and its parents are chosen by and trusted to the operator; do not use a directory writable by untrusted users.

Verify with `sha256sum -c SHA256SUMS` on Linux or `shasum -a 256 -c SHA256SUMS` on macOS, from inside the export. These hashes are not an authenticated signature. The tool does not encrypt files or upload them; choose encrypted local storage if required. Generated data paths and common credential files are excluded from Git by default, but inspect all staged changes before publishing.

## Next real-device validation

Use explicitly authorized lab devices and read-only accounts. Verify host-key rejection, one permitted and one denied command, the declared OS profile, long-output/paging behavior, a controlled timeout, selective retry and a private export. Inspect running configuration completeness and the manifest/file mapping. Any restoration test requires its own separate plan and authorization; this assistant does not restore configurations.
