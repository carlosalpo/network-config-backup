# Validation record — 2026-11-01

Preview version: **0.2.0rc1**. **Real-device validation is pending**, as requested by the owner. No EVE-NG, GNS3, production network, router or switch was contacted during this implementation.

The local suite currently contains 70 passing automated cases on Python 3.12. It covers:

- CSV/YAML/plain-host inventories, original inventory compatibility, malformed/duplicate fields, size limits, unsafe paths, unsupported platforms and credential fields.
- Platform query profiles, custom query restrictions, duplicate queries and missing device selections.
- Strict known_hosts configuration, password/SSH-key validation and explicit-only enable behavior.
- Per-query CLI failure classification; blank, paginated and limited output; connection/authentication failure isolation.
- Selected-query edits and retries, preserved successful timestamps, exclusion reasons, prior attempt history, cancellation before/during collection and operation locking.
- Private POSIX permissions, SHA-256 integrity, safe HTML rendering, unique exports, partial status, symlink destinations and injected write failures.
- Actual Textual interaction: global/group access profiles, scoped query selection, failed-query correction, partial export confirmation, compact 80×30 navigation and accidental discard prevention.
- The original `python backup.py` entry point and environment variable names.
- Real Netmiko connections to a **loopback-only Paramiko protocol fixture**: known host authentication, query/response handling, unknown host-key rejection and bad-password rejection. This is not a Cisco OS emulator or a real-device test.

The test fixture rejects external socket connections. GitHub Actions repeats tests, lint, formatting, package build and CLI entry-point checks on Python 3.11, 3.12 and 3.13. Consult the PR checks for their actual results; do not infer a passed remote run from this local record.

Actual application screenshots are generated from `DemoTransport` and explicitly marked synthetic. See [provenance](screenshots/provenance.json). They show functionality and layout, not proof of device compatibility.

Still pending: device/model/software-specific command coverage, real AAA policies, real paging/long outputs, network interruption behavior, SSH-key deployment in the lab, and manual comparison of collected configurations against device consoles. No restoration or connectivity certification is claimed.
