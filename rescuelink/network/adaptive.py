from collections import deque

class AdaptiveController:
    names = ["Fast", "Balanced", "Survival"]

    def __init__(self, policy="Auto"):
        self.policy = policy
        self.index = 0 if policy == "Auto" else self.names.index(policy.removeprefix("Fixed "))
        self.recent = deque(maxlen=12)
        self.bad = self.good = self.dwell = 0

    @property
    def mode(self):
        return self.names[self.index]

    def feedback(self, quality):
        """0 poor, 1 acceptable, 2 clean/high SNR. Never sees noise setting."""
        self.recent.append(quality)
        self.dwell += 1
        self.bad = self.bad + 1 if quality == 0 else 0
        self.good = self.good + 1 if quality == 2 else 0
        old = self.mode
        reason = ""
        if self.policy == "Auto" and self.dwell >= 3:
            if self.bad >= 2 and self.index < 2:
                self.index += 1
                reason = "two poor decoder/pilot reports or ACK timeouts"
            elif self.good >= 8 and self.index > 0:
                self.index -= 1
                reason = "eight clean high-SNR reports"
        if old != self.mode:
            self.dwell = self.bad = self.good = 0
            return old, self.mode, reason
        return None
