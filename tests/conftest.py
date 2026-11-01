import socket

import pytest


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """Tests may use loopback SSH fixtures, never lab/Internet targets."""
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError("External connections are forbidden in tests")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
