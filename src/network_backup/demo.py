"""Explicit offline fixtures. This adapter cannot create network connections."""


class DemoTransport:
    source_kind = "synthetic-demo; no device contacted"

    def connect(self, device, credential):
        return DemoConnection(device)

    def query(self, connection, command):
        if connection.device.name == "access-01" and command == "show running-config":
            return "% Authorization failed."
        if command.endswith("detailx"):
            return "% Invalid input detected at ^ marker."
        if command == "show running-config":
            return f"! SYNTHETIC FIXTURE - NOT A DEVICE BACKUP\nhostname {connection.device.name}\ninterface GigabitEthernet0/0\n description Example only\nend\n"
        return f"SYNTHETIC FIXTURE - NO DEVICE CONTACTED\nDevice: {connection.device.name}\nQuery: {command}\nSample response for demonstration only.\n"


class DemoConnection:
    def __init__(self, device):
        self.device = device

    def disconnect(self):
        pass
