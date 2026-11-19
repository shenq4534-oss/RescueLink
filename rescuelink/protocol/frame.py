from dataclasses import dataclass
from enum import IntEnum
import struct
import zlib
from rescuelink.config import MAX_PAYLOAD

class Kind(IntEnum):
    DATA = 1
    ACK = 2
    NACK = 3
    WINDOW_UPDATE = 4
    PROBE = 5
    LINK_REPORT = 6

HEADER = struct.Struct("!BBBBBIIHHHH")

@dataclass(frozen=True)
class Frame:
    kind: Kind
    src: int
    dst: int
    priority: int
    message_id: int
    sequence: int = 0
    index: int = 0
    count: int = 1
    window: int = 8
    payload: bytes = b""

    def validate(self):
        if self.kind not in list(Kind) or not 1 <= self.src <= 254 or not 1 <= self.dst <= 254:
            raise ValueError("type/address")
        if not 0 <= self.priority <= 2 or not 1 <= self.message_id <= 0xffffffff:
            raise ValueError("priority/message id")
        if not 0 <= self.sequence <= 0xffffffff or not 1 <= self.count <= 65535 or not 0 <= self.index < self.count:
            raise ValueError("sequence/fragment bounds")
        if not 0 <= self.window <= 64 or len(self.payload) > MAX_PAYLOAD:
            raise ValueError("window/payload bounds")
        if self.kind not in (Kind.DATA, Kind.LINK_REPORT) and self.payload:
            raise ValueError("control frames have no payload")
        if self.kind == Kind.LINK_REPORT and len(self.payload) != 3:
            raise ValueError("invalid link report")
        if self.kind == Kind.DATA and self.sequence != self.index:
            raise ValueError("sequence must equal fragment index within isolated message session")

    def pack(self):
        self.validate()
        raw = HEADER.pack(1, int(self.kind), self.src, self.dst, self.priority,
                          self.message_id, self.sequence, self.index, self.count,
                          self.window, len(self.payload)) + self.payload
        return raw + struct.pack("!I", zlib.crc32(raw))

    @classmethod
    def unpack(cls, raw):
        if len(raw) < HEADER.size + 4:
            raise ValueError("truncated")
        body, crc = raw[:-4], raw[-4:]
        if zlib.crc32(body) != struct.unpack("!I", crc)[0]:
            raise ValueError("CRC mismatch")
        v, k, s, d, p, mid, seq, idx, count, win, size = HEADER.unpack(body[:HEADER.size])
        if v != 1 or len(body) != HEADER.size + size:
            raise ValueError("version/length")
        f = cls(Kind(k), s, d, p, mid, seq, idx, count, win, body[HEADER.size:])
        f.validate()
        return f
