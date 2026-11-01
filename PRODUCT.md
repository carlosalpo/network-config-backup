# Network Configuration Backup

Audience: network engineers collecting configurations and diagnostic evidence from their own authorized Cisco devices. Mode: Operate. Product language: English; owner collaboration: Spanish.

The owner approved the four terminal mockups in the portfolio workspace, ui-concept-v1: credentials, command selection, failure review and export. The implementation adds their preceding inventory screen and uses an actual keyboard-operated Textual TUI, not a web portal. Netmiko is the selected SSH transport. Preserve the existing repository and `python backup.py` invocation while documenting its safer host-key handling and structured export format.

Success means an operator can import a device list, assign credentials globally/by group/by device, select scoped predefined/custom queries, see truthful per-query results, correct failed queries without repeating successes, and export a private complete or partial collection. Complete does not mean restoration tested.

The explicit offline demo must never contact devices. Real-device validation is deferred by the owner. Do not label fixture outputs or generated design concepts as live evidence. No automatic upload, secret persistence, restoration, NETCONF, scheduled collection or device configuration deployment in this preview.
