class BtWrapper:
    def __init__(self, kt_service):
        self._svc = kt_service

    def read(self, max_bytes=512):
        data = self._svc.read(max_bytes)
        return bytes(data) if data else b""

    def write(self, data: bytes):
        self._svc.write(data)

    def disconnect(self):
        self._svc.disconnect()