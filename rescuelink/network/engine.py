"""Single deterministic event clock, eight independent directed physical workers.

Only successfully decoded bytes cross a simulated cable's receive boundary.
Control reports, ACKs and application responses use the same physical pipeline.
"""
from dataclasses import asdict
from collections import Counter, deque
from pathlib import Path
import json
import threading
import heapq
import hashlib
from rescuelink.config import Config, MODES, HOSTS
from rescuelink.events import Event
from rescuelink.physical.channel import PhysicalLink
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.fragmentation import split
from rescuelink.protocol.transport import SendFlow, ReceiveFlow
from rescuelink.protocol.application import Message
from rescuelink.simulation.clock import Clock
from .adaptive import AdaptiveController
from .host import Host
from .switch import Switch
from .scheduler import PortQueue

class Network:
    def __init__(self, config=None, output_dir="outputs/received", fault=None, capture=False):
        self.config = config or Config()
        self.clock = Clock()
        self.hosts = {a: Host(a) for a in HOSTS}
        self.switch = Switch(self.hosts, self.config.scheduler)
        self.links, self.controllers, self.queues, self.busy = {}, {}, {}, {}
        for a in self.hosts:
            for direction in ("up", "down"):
                name = f"{direction}{a}"
                self.links[name] = PhysicalLink(self.config, self.config.seed + a*17 + (direction == "down")*101, name, capture)
                self.controllers[name] = AdaptiveController(self.config.policy)
                self.queues[name] = self.switch.queues[a] if direction == "down" else PortQueue("Priority")
                self.busy[name] = False
        self.flows, self.receivers = {}, {}
        self.next_id = 1
        self.events, self.attempts = [], []
        self.traces = deque(maxlen=80)
        self.stats = Counter()
        self.output_dir = Path(output_dir)
        self.fault = fault  # explicit integration-test-only loss hook, after real Cable
        self.lock = threading.RLock()
        self.closed = False
        self.activity_end = 0.0
        self.image_jobs = {}

    @property
    def now(self):
        return self.clock.now

    def log(self, kind, **kw):
        self.events.append(Event(self.now, kind, kw))

    def schedule(self, at, fn, *args):
        with self.lock:
            self.clock.at(at, fn, *args)

    def send(self, src, dst, message, priority=2, at=None):
        with self.lock:
            if self.closed:
                raise RuntimeError("network closed")
            if src not in self.hosts or not 1 <= dst <= 254 or not 0 <= priority <= 2:
                raise ValueError("invalid endpoint/priority")
            data = message.pack()
            parts = split(data, self.config.payload)
            mid = self.next_id
            self.next_id += 1
            if mid > 0xffffffff:
                raise ValueError("session id exhausted; reset network")
            frames = [Frame(Kind.DATA, src, dst, priority, mid, i, i, len(parts),
                            self.config.rx_capacity, p) for i, p in enumerate(parts)]
            t = self.now if at is None else at
            flow = SendFlow(src, dst, mid, frames, t, message.type, message.request_id,
                            advertised=self.config.rx_capacity)
            self.flows[mid] = flow
            self.clock.at(t, self._start, mid)
            return mid

    def _start(self, mid):
        f = self.flows[mid]
        self.log("generated", src=f.src, dst=f.dst, message_id=mid, app_type=f.app_type, fragments=len(f.frames))
        self._pump(f)

    def _arm(self, f):
        f.timer += 1
        # Conservative minimum RTT includes four hops, maximal mode and queued frames.
        max_frame = .363 + (self.config.payload+25)*16*64/48000
        queued = max(len(q) for q in self.queues.values())
        delay = max(self.config.rto, (self.config.window + queued + 2) * max_frame *
                    (2 + self.config.downlink_slowdown*2) + 4*self.config.length/2e8)
        self.clock.at(self.now + delay, self._timeout, f.message_id, f.timer)

    def _pump(self, f):
        if f.status != "sending" or self.now < f.generated:
            return
        window = 1 if self.config.transport == "Stop-and-Wait" else self.config.window
        limit = min(window, f.advertised)
        while f.next_seq < len(f.frames) and f.next_seq - f.base < limit:
            self._enqueue(f"up{f.src}", f.frames[f.next_seq])
            f.next_seq += 1
        self._arm(f)

    def _timeout(self, mid, token):
        f = self.flows[mid]
        if f.status != "sending" or f.timer != token:
            return
        self.log("timeout", src=f.src, message_id=mid, sequence=f.base, zero_window=f.advertised == 0)
        self._feedback(f"up{f.src}", 0)
        f.retries += 1
        if f.retries > self.config.max_retries:
            f.status, f.completed = "failed", self.now
            self.activity_end = max(self.activity_end, self.now)
            self.log("transfer_failed", message_id=mid, reason="retry limit", app_type=f.app_type)
            return
        if f.advertised == 0:
            probe = Frame(Kind.PROBE, f.src, f.dst, f.frames[0].priority, mid,
                          sequence=f.base, count=len(f.frames))
            self._enqueue(f"up{f.src}", probe)
        else:
            for seq in range(f.base, f.next_seq):
                self.stats["retransmissions"] += 1
                self.log("retransmission", message_id=mid, sequence=seq)
                self._enqueue(f"up{f.src}", f.frames[seq])
        self._arm(f)

    def _enqueue(self, lane, frame):
        self.queues[lane].push((frame, self.now))
        self.log("queued", lane=lane, src=frame.src, dst=frame.dst, message_id=frame.message_id,
                 sequence=frame.sequence, frame_type=frame.kind.name, priority=frame.priority,
                 queue_length=len(self.queues[lane]))
        if not self.busy[lane]:
            # Deferred dispatch allows all events at this instant to enter queues.
            self.busy[lane] = True
            self.clock.at(self.now, self._dispatch, lane)

    def _dispatch(self, lane):
        if not len(self.queues[lane]):
            self.busy[lane] = False
            return
        frame, enqueued = self.queues[lane].pop()
        mode = MODES["Survival"] if frame.kind == Kind.LINK_REPORT else MODES[self.controllers[lane].mode]
        slow = self.config.downlink_slowdown if lane.startswith("down") else 1
        result = self.links[lane].transmit(frame.pack(), mode, self.config.modulation, slow)
        end = self.now + result["duration"]
        arrival = end + result["propagation"]
        if self.fault and self.fault(lane, frame, len(self.attempts)):
            result.update(ok=False, raw=None, error="test injected loss AFTER original Cable")
        record = {k: v for k, v in result.items() if k not in ("tx", "rx", "raw", "trace", "tx_payload", "rx_payload")}
        record.update(start=self.now, end=end, arrival=arrival, lane=lane, mode=mode.name,
                      frame_type=frame.kind.name, src=frame.src, dst=frame.dst,
                      message_id=frame.message_id, sequence=frame.sequence, frame_bytes=len(frame.pack()),
                      queue_wait=self.now-enqueued, arrived=False)
        if "trace" in result:
            trace = result["trace"]
            trace.update(start=self.now, end=end, src=frame.src, dst=frame.dst,
                         message_id=frame.message_id, sequence=frame.sequence, frame_type=frame.kind.name)
            if not result["ok"]:
                trace.update(ok=False, error=result["error"], payload_hex_rx=None, frame_sha256_rx=None)
            self.traces.append(trace)
            record.update(frame_sha256_tx=trace["frame_sha256_tx"], frame_sha256_rx=trace["frame_sha256_rx"])
        self.attempts.append(record)
        self.stats["physical_transmissions"] += 1
        self.stats[frame.kind.name] += 1
        self.stats["corrected_codewords"] += result["corrected_codewords"]
        self.stats["detected_uncorrectable"] += result["detected_uncorrectable"]
        if not result["ok"]:
            self.stats["damaged_frames"] += 1
        self.log("physical_send", **record)
        self.clock.at(end, self._dispatch, lane)
        self.clock.at(arrival, self._arrive, lane, result, frame.kind == Kind.LINK_REPORT, record)

    def _arrive(self, lane, result, is_report, record=None):
        # PHY calculation happens at dispatch; this callback is the receive boundary.
        if record is not None:
            record["arrived"] = True
            self.log("physical_arrival", lane=lane, trace_id=result.get("trace_id"),
                     ok=result["ok"], error=result["error"])
        self.activity_end = max(self.activity_end, self.now)
        if not is_report:
            self._send_link_report(lane, result)
        if not result["ok"]:
            self.log("decode_rejected", lane=lane, reason=result["error"])
            return
        f = Frame.unpack(result["raw"])
        if lane.startswith("up"):
            port = int(lane[2:])
            if f.src != port:
                self.log("source_rejected", lane=lane)
                return
            if f.kind == Kind.LINK_REPORT and f.dst == 254:
                self._receive_link_report(f)
            elif f.dst not in self.switch.ports:
                self.log("unknown_destination", dst=f.dst, message_id=f.message_id)
                self.stats["unknown_destination"] += 1
            else:
                self.log("switch_forward", ingress=lane, egress=f"down{f.dst}",
                         src=f.src, dst=f.dst, message_id=f.message_id,
                         sequence=f.sequence, frame_type=f.kind.name,
                         frame_sha256=hashlib.sha256(result["raw"]).hexdigest())
                self._enqueue(f"down{f.dst}", f)
        else:
            if f.dst != int(lane[4:]):
                self.log("destination_rejected", lane=lane)
                return
            if f.kind == Kind.LINK_REPORT:
                self._receive_link_report(f)
            elif f.kind == Kind.DATA:
                self._receive_data(f)
            elif f.kind in (Kind.ACK, Kind.NACK, Kind.WINDOW_UPDATE):
                self._receive_ack(f)
            elif f.kind == Kind.PROBE:
                rx = self.receivers.get((f.dst, f.src, f.message_id))
                self._control(f, Kind.WINDOW_UPDATE, rx.expected if rx else 0)

    def _send_link_report(self, lane, result):
        up = lane.startswith("up")
        port = int(lane[2:] if up else lane[4:])
        snr = result["snr_linear"]
        quality = 0 if not result["ok"] or snr is None or snr < 1.0 else (2 if snr > 4 and result["corrected_codewords"] == 0 else 1)
        report = Frame(Kind.LINK_REPORT, 254 if up else port, port if up else 254, 0, 1,
                       payload=bytes([0 if up else 1, port, quality]))
        self._enqueue(f"down{port}" if up else f"up{port}", report)

    def _receive_link_report(self, f):
        direction, port, quality = f.payload
        if port not in self.hosts or direction not in (0, 1) or quality > 2:
            self.log("invalid_link_report")
            return
        # Authentic port correspondence: report about downlink arrives at switch, up at host.
        if (direction == 0 and (f.src != 254 or f.dst != port)) or (direction == 1 and (f.src != port or f.dst != 254)):
            return
        self._feedback(f"{'up' if direction == 0 else 'down'}{port}", quality)

    def _feedback(self, lane, quality):
        change = self.controllers[lane].feedback(quality)
        self.log("link_feedback", lane=lane, quality=quality, mode=self.controllers[lane].mode)
        if change:
            self.log("mode_changed", lane=lane, old=change[0], new=change[1], reason=change[2])

    def _control(self, data, kind, expected):
        free = self.config.rx_capacity - self.hosts[data.dst].rx_pending
        ack = Frame(kind, data.dst, data.src, data.priority, data.message_id,
                    expected, 0, data.count, free)
        self.log("window_advertised", host=data.dst, message_id=data.message_id, window=free, expected=expected)
        self._enqueue(f"up{data.dst}", ack)

    def _receive_data(self, f):
        key = (f.dst, f.src, f.message_id)
        rx = self.receivers.setdefault(key, ReceiveFlow(f.count, f.priority))
        if rx.count != f.count or rx.priority != f.priority:
            self.log("inconsistent_flow", message_id=f.message_id)
            return
        if f.sequence < rx.expected:
            self.stats["duplicates"] += 1
            self._control(f, Kind.ACK, rx.expected)
            return
        if f.sequence > rx.expected:
            self._control(f, Kind.NACK, rx.expected)
            return
        host = self.hosts[f.dst]
        if host.rx_pending >= self.config.rx_capacity:
            self._control(f, Kind.WINDOW_UPDATE, rx.expected)
            return
        host.rx_pending += 1
        rx.pending += 1
        rx.expected += 1
        self._control(f, Kind.ACK, rx.expected)
        self.clock.at(self.now + self.config.process_delay, self._consume, f, rx)

    def _consume(self, f, rx):
        self.activity_end = max(self.activity_end, self.now)
        host = self.hosts[f.dst]
        was_full = host.rx_pending >= self.config.rx_capacity
        host.rx_pending -= 1
        rx.pending -= 1
        try:
            raw = rx.assembled.add(f.index, f.count, f.payload)
            if raw is not None and not rx.delivered:
                m = Message.unpack(raw)
                rx.delivered = True
                # Only decoded/reassembled bytes enter this application boundary.
                host.received.append(dict(time=self.now, src=f.src, dst=f.dst, message_id=f.message_id,
                                          message=m, bytes=len(raw)))
                if f.message_id in self.flows:
                    self.flows[f.message_id].delivered = self.now
                self.stats["delivered_bits"] += len(m.body)*8
                self.log("application_received", src=f.src, dst=f.dst, message_id=f.message_id,
                         app_type=m.type, request_id=m.request_id, body_bytes=len(m.body))
                self._application(f, m)
        except ValueError as exc:
            self.log("application_error", message_id=f.message_id, reason=str(exc))
        if was_full:
            # Wake every zero-window flow at this host. Notification may itself be lost;
            # PROBE timer provides a second recovery path, also over cables.
            for (dst, src, mid), other in self.receivers.items():
                if dst == f.dst:
                    template = Frame(Kind.DATA, src, dst, other.priority, mid, 0, 0, other.count)
                    self._control(template, Kind.WINDOW_UPDATE, other.expected)

    def _receive_ack(self, ack):
        f = self.flows.get(ack.message_id)
        if not f or f.status != "sending" or ack.src != f.dst or ack.dst != f.src or ack.count != len(f.frames):
            return
        if not f.base <= ack.sequence <= f.next_seq:
            return
        progressed = ack.sequence > f.base
        f.advertised = ack.window
        if progressed:
            f.base = ack.sequence
            f.retries = 0
            f.nack_base = -1
        if f.base == len(f.frames):
            f.status, f.completed = "acked", self.now
            f.timer += 1
            self.log("transfer_acked", message_id=f.message_id)
        else:
            # One fast retransmit per base prevents duplicate NACK storms.
            if ack.kind == Kind.NACK and f.nack_base != f.base:
                f.nack_base = f.base
                for seq in range(f.base, f.next_seq):
                    self.stats["retransmissions"] += 1
                    self.log("retransmission", message_id=f.message_id, sequence=seq, reason="NACK")
                    self._enqueue(f"up{f.src}", f.frames[seq])
            self._pump(f)

    def _application(self, frame, message):
        from rescuelink.media.image_transfer import receive_image
        reply = None
        if message.type == "SOS_ALERT":
            reply = Message("SOS_ACK", message.request_id, {"accepted": True}, "救援请求已收到".encode())
        elif message.type == "STATUS_QUERY":
            reply = Message("STATUS_RESPONSE", message.request_id, {"host": frame.dst, "state": "online"})
        elif message.type.startswith("IMAGE_") and message.type != "IMAGE_RECEIVED":
            reply = receive_image(self, frame, message)
        elif message.type == "READY":
            self._image_next(message.request_id, message.meta.get("next", "preview"))
        elif message.type == "IMAGE_RECEIVED":
            self.log("image_confirmed", image_id=message.request_id, src=frame.src)
        if message.type == "ERROR":
            self.log("remote_error", request_id=message.request_id, meta=message.meta)
        if reply:
            self.send(frame.dst, frame.src, reply, frame.priority)

    def start_image(self, src, dst, data, progressive=True, at=None):
        from rescuelink.media.image_transfer import prepare_image
        with self.lock:
            image_id = f"img-{self.next_id}"
            meta, preview = prepare_image(data, image_id)
            self.image_jobs[image_id] = dict(src=src, dst=dst, data=data, preview=preview,
                                            meta=meta, progressive=progressive, stage="meta")
            self.send(src, dst, Message("IMAGE_META", image_id, meta), 1, at)
            return image_id

    def _image_next(self, image_id, stage):
        job = self.image_jobs.get(image_id)
        if not job:
            return
        if stage == "preview" and job["stage"] == "meta":
            job["stage"] = "preview"
            if job["progressive"]:
                self.send(job["src"], job["dst"], Message("IMAGE_PREVIEW", image_id, {}, job["preview"]), 1)
            else:
                self._image_next(image_id, "original")
        elif stage == "original" and job["stage"] == "preview":
            job["stage"] = "original"
            self.send(job["src"], job["dst"], Message("IMAGE_ORIGINAL", image_id, {}, job["data"]), 2)

    def step(self, count=1):
        with self.lock:
            if self.closed:
                return False
            for _ in range(count):
                while self.clock.events:
                    _, _, fn, args = self.clock.events[0]
                    if fn == self._timeout:
                        flow = self.flows[args[0]]
                        if flow.status != "sending" or flow.timer != args[1]:
                            heapq.heappop(self.clock.events)
                            continue
                    break
                if not self.clock.step():
                    return False
            return bool(self.clock.events)

    def run(self, max_events=300000):
        for _ in range(max_events):
            if not self.step():
                return self.summary()
        raise RuntimeError("event budget exhausted; state retained for diagnosis")

    def set_noise(self, value):
        if not 0 <= value <= 10:
            raise ValueError("noise bounds")
        for link in self.links.values():
            link.cable.noise_level = value
        self.log("channel_changed", noise=value)

    def summary(self):
        with self.lock:
            relevant = list(self.flows.values())
            duration = max(self.activity_end, 1e-9)
            delivered = sum(f.delivered is not None for f in relevant)
            return dict(config=asdict(self.config), simulated_seconds=duration,
                        generated=len(relevant), delivered=delivered,
                        success_rate=delivered/len(relevant) if relevant else 0,
                        acked=sum(f.status == "acked" for f in relevant),
                        failed=sum(f.status == "failed" for f in relevant),
                        goodput_bps=self.stats["delivered_bits"]/duration,
                        queue_peak={k:q.peak for k,q in self.queues.items()},
                        modes={k:c.mode for k,c in self.controllers.items()},
                        mode_changes=[e.asdict() for e in self.events if e.kind == "mode_changed"],
                        **dict(self.stats))

    def export(self, directory):
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=True)
        (p/"summary.json").write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        (p/"events.jsonl").write_text("\n".join(json.dumps(e.asdict(), ensure_ascii=False) for e in self.events), encoding="utf-8")
        (p/"physical_attempts.json").write_text(json.dumps(self.attempts, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self):
        with self.lock:
            if not self.closed:
                for f in self.flows.values():
                    if f.status == "sending":
                        f.status = "cancelled"
                self.closed = True
                self.clock.events.clear()
                for link in self.links.values():
                    link.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
