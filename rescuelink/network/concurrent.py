"""Thread-safe producer submissions and an explicitly stoppable engine runner."""
import threading
import queue

class Runner:
    def __init__(self, network):
        self.network = network
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.error = None
        self.thread = None

    def submit(self, src, dst, message, priority=2):
        if self.stop_event.is_set():
            raise RuntimeError("runner stopped")
        self.commands.put((src, dst, message, priority))

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="rescuelink-engine", daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while not self.stop_event.is_set():
                try:
                    args = self.commands.get(timeout=0.01 if not self.network.clock.events else 0)
                    self.network.send(*args)
                    self.commands.task_done()
                except queue.Empty:
                    pass
                self.network.step(16)
        except Exception as exc:
            self.error = repr(exc)
            self.stop_event.set()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError("worker failed to terminate")
        self.network.close()
