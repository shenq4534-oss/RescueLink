from dataclasses import dataclass

SAMPLE_RATE = 48000
MAX_PAYLOAD = 256
MAX_MESSAGE = 2 * 1024 * 1024
HOSTS = {1: "A · 状态", 2: "B · 图片", 3: "C · SOS", 4: "D · 指挥中心"}

@dataclass(frozen=True)
class Mode:
    name: str
    spb: int
    fec: bool

MODES = {"Fast": Mode("Fast", 8, False),
         "Balanced": Mode("Balanced", 16, True),
         "Survival": Mode("Survival", 64, True)}

@dataclass
class Config:
    seed: int = 42
    noise: float = 0.15
    policy: str = "Auto"
    scheduler: str = "Priority"
    transport: str = "GBN"
    window: int = 4
    rx_capacity: int = 8
    process_delay: float = 0.002
    payload: int = 256
    rto: float = 8.0
    max_retries: int = 10
    downlink_slowdown: float = 1.0
    length: float = 100.0
    attenuation: float = 0.1
    modulation: str = "BPSK"

    def __post_init__(self):
        if self.policy not in ("Auto", "Fixed Fast", "Fixed Balanced", "Fixed Survival"):
            raise ValueError("unknown policy")
        if self.scheduler not in ("FIFO", "Priority") or self.transport not in ("GBN", "Stop-and-Wait"):
            raise ValueError("unknown scheduler/transport")
        if not (1 <= self.window <= 64 and 1 <= self.rx_capacity <= 64 and 1 <= self.payload <= MAX_PAYLOAD):
            raise ValueError("window/capacity/payload out of range")
        if not (0 <= self.noise <= 10 and self.rto > 0 and self.process_delay >= 0 and 0 <= self.max_retries <= 100):
            raise ValueError("invalid channel/timer")
        if self.length < 0 or self.attenuation < 0 or self.downlink_slowdown < 1:
            raise ValueError("invalid link parameters")
        if self.modulation not in ("BPSK", "ASK", "BFSK"):
            raise ValueError("unknown modulation")
