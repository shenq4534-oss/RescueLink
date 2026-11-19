from dataclasses import dataclass, field

@dataclass
class Host:
    address: int
    received: list = field(default_factory=list)
    images: dict = field(default_factory=dict)
    rx_pending: int = 0
