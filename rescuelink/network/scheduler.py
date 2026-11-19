from collections import deque

class PortQueue:
    """Non-preemptive; serve oldest ordinary frame after three urgent frames."""
    def __init__(self, policy="Priority"):
        self.policy, self.items, self.urgent_run = policy, deque(), 0
        self.peak = 0

    def push(self, item):
        self.items.append(item)
        self.peak = max(self.peak, len(self.items))

    def pop(self):
        if self.policy == "FIFO":
            return self.items.popleft()
        # item = (frame, enqueue time); flow priority is immutable.
        normal = [i for i, (f, _) in enumerate(self.items) if f.priority == 2]
        if normal and self.urgent_run >= 3:
            idx = normal[0]
        else:
            idx = min(range(len(self.items)), key=lambda i: self.items[i][0].priority)
        item = self.items[idx]
        del self.items[idx]
        self.urgent_run = self.urgent_run + 1 if item[0].priority < 2 else 0
        return item

    def __len__(self):
        return len(self.items)
