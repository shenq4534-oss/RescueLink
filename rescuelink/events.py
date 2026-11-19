from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Event:
    time: float
    kind: str
    details: dict

    def asdict(self):
        return dict(time=self.time, kind=self.kind, **self.details)
