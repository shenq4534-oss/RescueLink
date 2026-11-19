from .scheduler import PortQueue

class Switch:
    def __init__(self, addresses, policy):
        self.ports = set(addresses)
        self.queues = {a: PortQueue(policy) for a in addresses}
