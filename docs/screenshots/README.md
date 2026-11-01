# Actual application captures

These SVG images are exported from the real Textual application by `scripts/capture.py`. They use the explicit `--demo` adapter and documentation IP addresses. No devices were contacted, and no real configuration or credential is present.

- `inventory.svg`: preview the imported sample devices.
- `credentials.svg`: group assignment and masked in-memory credentials.
- `commands.svg`: platform profiles and custom queries.
- `review.svg`: passed, invalid-command and permission-denied results.
- `save.svg`: clearly marked partial synthetic export preview.
- `save-compact.svg`: the same export flow at 80×30 terminal cells, with scrolling.

`provenance.json` records the application version, method, dimensions and file hashes. Generation timestamps inside SVG metadata and collection timestamps refer to the fixture run, not to a live validation campaign. The approved AI design concepts are not substituted for these application captures.

Recreate after installing development dependencies:

```bash
python scripts/capture.py
```
