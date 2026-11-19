"""Length-delimited strict JSON metadata + opaque binary body."""
import json
import struct
from dataclasses import dataclass
from rescuelink.config import MAX_MESSAGE

TYPES = {"TEXT", "SOS_ALERT", "SOS_ACK", "IMAGE_META", "READY", "ERROR", "IMAGE_PREVIEW",
         "IMAGE_ORIGINAL", "IMAGE_RECEIVED", "STATUS_QUERY", "STATUS_RESPONSE"}
RESPONSES = {"SOS_ACK", "READY", "ERROR", "IMAGE_RECEIVED", "STATUS_RESPONSE"}

@dataclass
class Message:
    type: str
    request_id: str
    meta: dict
    body: bytes = b""

    def pack(self):
        if self.type not in TYPES or not isinstance(self.request_id, str) or not 1 <= len(self.request_id) <= 64:
            raise ValueError("application type/id")
        h = json.dumps(dict(type=self.type, request_id=self.request_id, meta=self.meta),
                       ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        if len(h) > 8192 or len(h) + len(self.body) + 4 > MAX_MESSAGE:
            raise ValueError("application size")
        return struct.pack("!I", len(h)) + h + self.body

    @classmethod
    def unpack(cls, raw):
        if len(raw) < 4 or len(raw) > MAX_MESSAGE:
            raise ValueError("application length")
        n = struct.unpack("!I", raw[:4])[0]
        if not 1 <= n <= 8192 or 4 + n > len(raw):
            raise ValueError("metadata length")
        try:
            d = json.loads(raw[4:4+n].decode("utf-8"))
            if set(d) != {"type", "request_id", "meta"} or not isinstance(d["meta"], dict):
                raise ValueError("application schema")
            m = cls(d["type"], d["request_id"], d["meta"], raw[4+n:])
            m.pack()
            return m
        except (UnicodeError, KeyError, TypeError, json.JSONDecodeError) as e:
            raise ValueError("invalid application") from e
