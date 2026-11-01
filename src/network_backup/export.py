"""Private, atomic exports. Sensitive original outputs never enter reports or Git."""

import hashlib
import html
import json
import os
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .model import now


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def export_collection(collection, destination):
    if not collection._lock.acquire(blocking=False):
        raise ValueError("Wait for collection to finish before exporting.")
    try:
        return _export_locked(collection, destination)
    finally:
        collection._lock.release()


def _export_locked(collection, destination):
    if not any(r.status == "passed" for r in collection.results.values()):
        raise ValueError("No successful captures to export.")
    target = Path(destination).expanduser()
    if not str(destination).strip() or target.is_symlink():
        raise ValueError("Choose a real destination folder, not a symbolic link.")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = target.resolve(strict=True)
    if not target.is_dir():
        raise ValueError("Destination must be a directory.")
    name = datetime.now(timezone.utc).strftime("backup-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    staging = Path(tempfile.mkdtemp(prefix=".ncb-incomplete-", dir=target))
    records, hashes = [], {}
    try:
        for index, result in enumerate(collection.results.values(), 1):
            device = result.job.device
            record = dict(
                device=asdict(device),
                command=result.job.command,
                status=result.status,
                captured_at=result.captured_at,
                message=result.message,
                attempts=result.attempts,
                excluded_reason=result.excluded_reason,
                file=None,
            )
            if result.status == "passed":
                path = (
                    Path("sites")
                    / device.site
                    / device.name
                    / result.job.category
                    / f"{index:04d}.txt"
                )
                payload = result.output.encode("utf-8")
                private_write(staging / path, payload)
                record["file"] = path.as_posix()
                hashes[path.as_posix()] = hashlib.sha256(payload).hexdigest()
            records.append(record)
        manifest = dict(
            schema_version=1,
            created_at=now(),
            status="complete" if collection.complete else "partial",
            meaning="Complete means all planned queries passed, not restoration verified.",
            real_device_validation="pending for this application release",
            source=collection.source,
            queries=records,
            sha256=hashes,
        )
        payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
        private_write(staging / "manifest.json", payload)
        rows = "".join(
            "<tr>"
            + "".join(
                "<td>" + html.escape(str(value)) + "</td>"
                for value in (
                    r["device"]["name"],
                    r["command"],
                    r["status"],
                    r["captured_at"] or "",
                    r["excluded_reason"] or r["message"],
                    r["file"] or "",
                )
            )
            + "</tr>"
            for r in records
        )
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "style-src 'unsafe-inline'\">"
            "<title>Network Configuration Backup report</title>"
            "<style>body{font:16px system-ui;margin:2rem;background:#1c2126;color:#edf2f6}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #657783;"
            "padding:.6rem;text-align:left;overflow-wrap:anywhere}h1{color:#65cfda}</style>"
            "<h1>Network Configuration Backup</h1><p>Source: "
            + html.escape(collection.source)
            + ". Collection: "
            + manifest["status"]
            + ". A capture is not a restoration test. Original outputs may contain secrets.</p>"
            "<table><thead><tr><th>Device</th><th>Query</th><th>Result</th><th>UTC timestamp</th>"
            "<th>Detail</th><th>Output file</th></tr></thead><tbody>"
            + rows
            + "</tbody></table></html>"
        )
        private_write(staging / "summary.html", page.encode())
        # manifest hashes cover captures; this checksum file also covers the manifest and report.
        for filename in ("manifest.json", "summary.html"):
            hashes[filename] = hashlib.sha256((staging / filename).read_bytes()).hexdigest()
        private_write(
            staging / "SHA256SUMS",
            "".join(f"{digest}  {path}\n" for path, digest in sorted(hashes.items())).encode(),
        )
        for folder in staging.rglob("*"):
            if folder.is_dir():
                os.chmod(folder, 0o700)
        os.rename(staging, target / name)
        return target / name
    except Exception:
        # Keep an incomplete private directory for recovery; never advertise it as a finished backup.
        raise OSError(
            "Export did not finish. Private .ncb-incomplete-* files may remain in the destination; previous backups are unchanged."
        ) from None
