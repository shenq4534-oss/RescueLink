from rescuelink.config import MAX_MESSAGE, MAX_PAYLOAD

def split(data, size=256):
    if not 1 <= size <= MAX_PAYLOAD or len(data) > MAX_MESSAGE:
        raise ValueError("message/fragment limit")
    return [data[i:i+size] for i in range(0, len(data), size)] or [b""]

class Reassembler:
    def __init__(self, count):
        if not 1 <= count <= 65535:
            raise ValueError("invalid fragment count")
        self.count, self.parts, self.size = count, {}, 0

    def add(self, index, count, payload):
        if count != self.count or not 0 <= index < count or len(payload) > MAX_PAYLOAD:
            raise ValueError("inconsistent fragments")
        if index in self.parts and self.parts[index] != payload:
            raise ValueError("conflicting duplicate")
        if index not in self.parts:
            if self.size + len(payload) > MAX_MESSAGE:
                raise ValueError("reassembly overflow")
            self.parts[index] = payload
            self.size += len(payload)
        return b"".join(self.parts[i] for i in range(count)) if len(self.parts) == count else None
