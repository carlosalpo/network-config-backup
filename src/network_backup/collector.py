"""Bounded sequential SSH collection. No configuration changes or automatic retries."""

import re
import threading
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException, ReadTimeout
from paramiko import BadHostKeyException, SSHException

from .commands import validate_command
from .model import Credential, Result

MAX_OUTPUT = 8 * 1024 * 1024
MAX_COLLECTION = 64 * 1024 * 1024
ERRORS = [
    (
        "permission_denied",
        re.compile(
            r"(?im)^\s*(?:%\s*)?(?:authorization failed|permission denied|access denied|"
            r"not authorized|insufficient privileges|command authorization failed|"
            r"user not authorized|you do not have permission).*$"
        ),
    ),
    (
        "invalid_command",
        re.compile(
            r"(?im)^\s*(?:%\s*)?(?:invalid (?:input|command)|incomplete command|"
            r"ambiguous command|unknown command|unrecognized command|syntax error).*$"
        ),
    ),
    ("device_error", re.compile(r"(?im)^\s*%\s*(?:error|failed|unable|cannot).*$")),
    ("incomplete", re.compile(r"--\s*More\s*--|(?im:^\s*(?:output truncated|\[truncated\]).*$)")),
]
MESSAGES = {
    "passed": "Query returned a prompt without a recognized CLI error; not a restore test.",
    "permission_denied": "Device denied this query. Review the credential profile and AAA policy.",
    "invalid_command": "Device rejected this query. Edit it or exclude it with a reason.",
    "device_error": "Device reported an error; inspect the query on the device before retrying.",
    "incomplete": "Output appears incomplete or paginated. Review the device session.",
    "empty": "Empty output; collection cannot be marked passed.",
}


def classify(output):
    if not isinstance(output, str) or not output.strip():
        return "empty"
    for status, pattern in ERRORS:
        if pattern.search(output):
            return status
    return "passed"


class NetmikoTransport:
    """Reject unknown/changed host keys; never enroll keys or enable services."""

    def __init__(self, known_hosts=None, timeout=30, connector=ConnectHandler):
        if not 5 <= timeout <= 120:
            raise ValueError("Command timeout must be 5–120 seconds.")
        self.known_hosts = str(Path(known_hosts or "~/.ssh/known_hosts").expanduser())
        self.timeout = timeout
        self.connector = connector

    def connect(self, device, credential):
        credential.validate()
        if not Path(self.known_hosts).is_file():
            raise ValueError("Choose an existing verified SSH known_hosts file.")
        options = dict(
            device_type=device.platform,
            host=device.host,
            port=device.port,
            username=credential.username,
            password=credential.password,
            secret=credential.secret,
            use_keys=bool(credential.key_file),
            key_file=str(Path(credential.key_file).expanduser()) if credential.key_file else None,
            passphrase=credential.passphrase or None,
            allow_agent=False,
            ssh_strict=True,
            system_host_keys=False,
            alt_host_keys=True,
            alt_key_file=self.known_hosts,
            conn_timeout=10,
            auth_timeout=15,
            banner_timeout=15,
            read_timeout_override=self.timeout,
            session_timeout=30,
            session_log=None,
            allow_auto_change=False,
        )
        connection = self.connector(**options)
        try:
            if credential.secret:
                connection.enable()
        except Exception:
            connection.disconnect()
            raise
        return connection

    def query(self, connection, command):
        return connection.send_command(
            validate_command(command),
            read_timeout=self.timeout,
            cmd_verify=True,
            strip_prompt=True,
            strip_command=True,
        )


def connection_error(exc):
    # Never forward exception text: it may contain credentials, banners or device output.
    if isinstance(exc, NetmikoAuthenticationException):
        return "authentication_failed", "Authentication failed; review this credential profile."
    if isinstance(exc, BadHostKeyException):
        return "host_key_failed", "SSH host key changed; verify it outside the assistant."
    if isinstance(exc, SSHException) and "known_hosts" in str(exc):
        return "host_key_failed", "SSH host key is unknown; verify it outside the assistant."
    if isinstance(exc, (NetmikoTimeoutException, TimeoutError, OSError)):
        return "connection_failed", "SSH connection failed or timed out; check address and access."
    if isinstance(exc, ValueError):
        return "access_setup_failed", "Check the credential fields and verified known_hosts file."
    return "connection_failed", "Session setup failed; check SSH identity, access and platform."


class Collection:
    def __init__(self, jobs, transport=None):
        if not jobs or len({j.id for j in jobs}) != len(jobs):
            raise ValueError("A collection requires unique planned queries.")
        self.results = {job.id: Result(job) for job in jobs}
        self.transport = transport or NetmikoTransport()
        self.source = getattr(self.transport, "source_kind", "SSH collection")
        self.cancel = threading.Event()
        self._lock = threading.Lock()

    @property
    def busy(self):
        return self._lock.locked()

    @property
    def complete(self):
        return bool(self.results) and all(r.status == "passed" for r in self.results.values())

    def edit(self, key, command):
        if self.busy:
            raise ValueError("Wait for collection to finish before editing.")
        command = validate_command(command)
        result = self.results[key]
        if result.status in {"passed", "pending"}:
            raise ValueError("Only failed or excluded queries can be edited here.")
        if any(
            r.job.device.name == result.job.device.name
            and r.job.command.lower() == command.lower()
            and k != key
            for k, r in self.results.items()
        ):
            raise ValueError("This device already has that query in its plan.")
        result.begin_attempt()
        result.job = replace(
            result.job,
            command=command,
            category=(
                "configuration"
                if command.lower() in {"show running-config", "show startup-config"}
                else "diagnostics"
            ),
        )
        result.status, result.message, result.captured_at = (
            "pending",
            "Edited; not collected.",
            None,
        )

    def exclude(self, key, reason):
        if self.busy:
            raise ValueError("Wait for collection to finish before excluding a query.")
        if not reason.strip() or len(reason) > 240 or any(ord(c) < 32 for c in reason):
            raise ValueError("Enter a one-line exclusion reason, at most 240 characters.")
        result = self.results[key]
        result.begin_attempt()
        result.excluded_reason = reason.strip()
        result.finish("excluded", "Excluded by the operator; see the recorded reason.")

    def collect(self, credentials: dict[str, Credential], keys=None, progress=lambda: None):
        if not self._lock.acquire(blocking=False):
            raise ValueError("A collection is already running.")
        try:
            selected = list(self.results) if keys is None else list(keys)
            if any(k not in self.results for k in selected):
                raise ValueError("Unknown collection query.")
            pending = [
                self.results[k]
                for k in selected
                if self.results[k].status not in {"passed", "excluded"}
            ]
            grouped = defaultdict(list)
            for result in pending:
                grouped[result.job.device.name].append(result)
            for name, results in grouped.items():
                if self.cancel.is_set():
                    break
                connection = None
                try:
                    credential = credentials.get(name)
                    if credential is None:
                        raise ValueError("Missing profile")
                    connection = self.transport.connect(results[0].job.device, credential)
                except Exception as exc:
                    status, message = connection_error(exc)
                    for result in results:
                        result.begin_attempt()
                        result.finish(status, message)
                    progress()
                    continue
                try:
                    for index, result in enumerate(results):
                        if self.cancel.is_set():
                            break
                        result.begin_attempt()
                        try:
                            output = self.transport.query(connection, result.job.command)
                            size = len(output.encode("utf-8"))
                            total = sum(
                                len(r.output.encode("utf-8")) for r in self.results.values()
                            )
                            if size > MAX_OUTPUT or total + size > MAX_COLLECTION:
                                result.finish(
                                    "output_limit", "Output exceeded the collection size limit."
                                )
                            else:
                                status = classify(output)
                                # Rejected output is not stored or echoed: banners may contain secrets.
                                result.finish(
                                    status, MESSAGES[status], output if status == "passed" else ""
                                )
                        except Exception as exc:
                            status = (
                                "timeout"
                                if isinstance(exc, (ReadTimeout, TimeoutError))
                                else "session_failed"
                            )
                            result.finish(
                                status, "Query did not finish reliably. Reconnect before retrying."
                            )
                            # Never reuse a stream after timeout: late output could be assigned to another command.
                            for remaining in results[index + 1 :]:
                                remaining.begin_attempt()
                                remaining.finish(
                                    "session_failed",
                                    "Not sent: the earlier query lost session synchronization.",
                                )
                            break
                        finally:
                            progress()
                finally:
                    try:
                        connection.disconnect()
                    except Exception:
                        pass
            if self.cancel.is_set():
                for result in pending:
                    if result.status == "pending":
                        result.finish(
                            "cancelled", "Not sent: collection cancelled by the operator."
                        )
                progress()
        finally:
            self._lock.release()
