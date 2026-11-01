"""Real Netmiko + Paramiko on loopback; protocol fixture, not Cisco emulation certification."""

import socket
import threading
import time
from contextlib import contextmanager

import paramiko
import pytest

from network_backup.collector import Collection, NetmikoTransport
from network_backup.commands import make_jobs
from network_backup.model import Credential, Device


@contextmanager
def ssh_fixture(tmp_path, trusted=True, password="fixture-password"):
    key = paramiko.RSAKey.generate(2048)
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(5)
    port = server.getsockname()[1]
    known = tmp_path / "known_hosts"
    known.write_text(f"[127.0.0.1]:{port} {key.get_name()} {key.get_base64()}\n" if trusted else "")
    commands = []
    stop = threading.Event()

    class Auth(paramiko.ServerInterface):
        def check_auth_password(self, username, supplied):
            return (
                paramiko.AUTH_SUCCESSFUL
                if (username, supplied) == ("reader", password)
                else paramiko.AUTH_FAILED
            )

        def get_allowed_auths(self, username):
            return "password"

        def check_channel_request(self, kind, chanid):
            return (
                paramiko.OPEN_SUCCEEDED
                if kind == "session"
                else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
            )

        def check_channel_pty_request(self, *args):
            return True

        def check_channel_shell_request(self, channel):
            return True

    def serve():
        transport = None
        try:
            client, _ = server.accept()
            transport = paramiko.Transport(client)
            transport.add_server_key(key)
            transport.start_server(server=Auth())
            channel = transport.accept(5)
            if channel is None:
                return
            channel.settimeout(0.2)
            time.sleep(0.1)
            channel.send(b"fixture#")
            buffer = b""
            while not stop.is_set() and transport.is_active():
                try:
                    data = channel.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                buffer += data.replace(b"\r", b"\n")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    command = line.decode().strip()
                    if command:
                        commands.append(command)
                    if command == "exit":
                        return
                    if command == "show running-config":
                        output = "! protocol fixture only\nhostname fixture\nend"
                    elif command == "show interfaces":
                        output = "% Invalid input detected at ^ marker."
                    else:
                        output = ""
                    channel.send(
                        (command + "\r\n" + output.replace("\n", "\r\n") + "\r\nfixture#").encode()
                    )
        except (EOFError, OSError, paramiko.SSHException):
            pass
        finally:
            if transport:
                transport.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield Device("fixture", "127.0.0.1", "cisco_ios", port=port), known, commands
    finally:
        stop.set()
        server.close()
        thread.join(6)


def test_netmiko_real_ssh_collects_and_classifies(tmp_path):
    with ssh_fixture(tmp_path) as (device, known, commands):
        jobs = make_jobs(
            [device],
            {
                "fixture": [
                    ("show running-config", "configuration"),
                    ("show interfaces", "diagnostics"),
                ]
            },
        )
        run = Collection(jobs, NetmikoTransport(known, timeout=5))
        run.collect({"fixture": Credential("reader", "fixture-password")})
        values = list(run.results.values())
        assert [r.status for r in values] == ["passed", "invalid_command"]
        assert "hostname fixture" in values[0].output
        assert commands.count("show running-config") == 1
        assert not any(c in {"configure terminal", "write memory"} for c in commands)


@pytest.mark.parametrize(
    "trusted,password,status",
    [(False, "fixture-password", "host_key_failed"), (True, "incorrect", "authentication_failed")],
)
def test_netmiko_rejects_unknown_host_and_bad_credentials(tmp_path, trusted, password, status):
    with ssh_fixture(tmp_path, trusted=trusted) as (device, known, commands):
        run = Collection(
            make_jobs([device], {"fixture": [("show version", "diagnostics")]}),
            NetmikoTransport(known, timeout=5),
        )
        run.collect({"fixture": Credential("reader", password)})
        result = next(iter(run.results.values()))
        assert result.status == status
        assert not commands
