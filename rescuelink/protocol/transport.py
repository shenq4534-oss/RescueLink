from dataclasses import dataclass, field
from .frame import Frame
from .fragmentation import Reassembler

@dataclass
class SendFlow:
    src: int
    dst: int
    message_id: int
    frames: list[Frame]
    generated: float
    app_type: str
    request_id: str
    base: int = 0
    next_seq: int = 0
    advertised: int = 1
    retries: int = 0
    timer: int = 0
    status: str = "sending"
    completed: float | None = None
    delivered: float | None = None
    nack_base: int = -1

@dataclass
class ReceiveFlow:
    count: int
    priority: int
    expected: int = 0
    pending: int = 0
    assembled: Reassembler = field(init=False)
    delivered: bool = False

    def __post_init__(self):
        self.assembled = Reassembler(self.count)
