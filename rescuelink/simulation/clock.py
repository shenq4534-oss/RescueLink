import heapq
import itertools

class Clock:
    def __init__(self):
        self.now = 0.0
        self.events = []
        self.ids = itertools.count()

    def at(self, when, callback, *args):
        if when < self.now - 1e-9:
            raise ValueError("event in the past")
        heapq.heappush(self.events, (max(self.now, when), next(self.ids), callback, args))

    def step(self):
        if not self.events:
            return False
        self.now, _, fn, args = heapq.heappop(self.events)
        fn(*args)
        return True
