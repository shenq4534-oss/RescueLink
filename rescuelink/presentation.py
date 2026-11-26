"""Read-only presentation models and a real, stepwise Level 1 session.

No Streamlit dependency. These views never synthesize a successful reception.
"""
from html import escape
from math import isfinite

from rescuelink.config import Config, HOSTS, MODES
from rescuelink.physical.channel import PhysicalLink
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.fragmentation import Reassembler, split


class PointToPointSession:
    """One original Cable transmission per step, including framing and CRC."""

    def __init__(self, data, config=None, mode="Balanced"):
        self.config = config or Config()
        self.data = data
        self.parts = split(data, self.config.payload)
        self.mode = MODES[mode]
        self.link = PhysicalLink(self.config, self.config.seed, "A-to-B")
        self.reassembler = Reassembler(len(self.parts))
        self.records = []
        self.received = None
        self.now = 0.0
        self.closed = False

    @property
    def done(self):
        return len(self.records) == len(self.parts)

    @property
    def success(self):
        return self.done and self.received == self.data

    def step(self):
        if self.done or self.closed:
            return False
        i = len(self.records)
        frame = Frame(Kind.DATA, 1, 2, 2, 1, i, i, len(self.parts), payload=self.parts[i])
        result = self.link.transmit(frame.pack(), self.mode, self.config.modulation)
        self.now += result["duration"] + result["propagation"]
        record = {k: v for k, v in result.items()
                  if k not in ("raw", "tx", "rx", "tx_payload", "rx_payload")}
        record.update(index=i, payload_bytes=len(self.parts[i]), arrival=self.now)
        self.records.append(record)
        if result["ok"]:
            recovered = Frame.unpack(result["raw"])
            self.received = self.reassembler.add(recovered.index, recovered.count, recovered.payload)
        if self.done:
            self.close()
        return not self.done

    def close(self):
        if not self.closed:
            self.link.close()
            self.closed = True


def fmt(value, digits=1, suffix=""):
    if value is None or not isfinite(float(value)):
        return "—"
    return f"{value:,.{digits}f}{suffix}"


def image_snapshot(net):
    """Only received image state; sender jobs supply metadata/progress, never pixels."""
    candidates = [(im["metadata_time"], src, dst, iid, im)
                  for dst, host in net.hosts.items()
                  for (src, iid), im in host.images.items()]
    # A newly submitted job must not inherit the previous job's verified image.
    if net.image_jobs:
        latest_id = next(reversed(net.image_jobs))
        candidates = [row for row in candidates if row[3] == latest_id]
    if not candidates:
        job = next(reversed(net.image_jobs.values()), None) if net.image_jobs else None
        return dict(state="pending" if job else "empty", preview=None, original=None,
                    progress=0.0, acked=0, fragments=0, image=None,
                    label="正在发送元信息" if job else "等待现场图像")
    _, src, dst, iid, im = max(candidates, key=lambda row: row[0])
    flow = next((f for f in reversed(list(net.flows.values()))
                 if f.request_id == iid and f.app_type == "IMAGE_ORIGINAL"), None)
    total = len(flow.frames) if flow else 0
    acked = flow.base if flow else 0
    failed = any(f.status in ("failed", "cancelled") and f.request_id == iid
                 for f in net.flows.values())
    failed = failed or any(e.kind == "image_error" and e.details.get("image_id") == iid
                           for e in net.events)
    state = ("verified" if im["verified"] else "failed" if failed
             else "preview" if im["preview"] is not None else "pending")
    labels = {"verified": "原图已完整校验", "failed": "任务未完成", "preview": "预览已到达 · 原图传输中",
              "pending": "元信息已接收 · 等待图像"}
    return dict(state=state, preview=im["preview"],
                original=im["original"] if im["verified"] else None,
                progress=1.0 if im["verified"] else acked/total if total else 0.0,
                acked=acked, fragments=total, image=im, label=labels[state],
                src=src, dst=dst, image_id=iid)


def milestone_reached(net, target):
    if target == "preview":
        return any(im["preview"] is not None for h in net.hosts.values() for im in h.images.values())
    if target == "sos":
        return any(f.app_type == "SOS_ALERT" and f.delivered is not None for f in net.flows.values())
    if target == "image":
        return any(im["verified"] for h in net.hosts.values() for im in h.images.values())
    return False


def advance(net, count=12, target=None):
    """Stop at an actual reception boundary, before advancing another event."""
    if target and milestone_reached(net, target):
        return False, True
    more = not net.closed and bool(net.clock.events)
    for _ in range(count):
        if not more:
            break
        more = net.step()
        if target and milestone_reached(net, target):
            return more, True
    return more, False


EVENT_LABELS = {
    "generated": ("任务提交", "neutral"),
    "preview_available": ("预览到达", "success"),
    "image_complete": ("原图校验完成", "success"),
    "image_confirmed": ("发送方收到回执", "success"),
    "mode_changed": ("保护模式切换", "warning"),
    "channel_changed": ("信道条件变化", "warning"),
    "retransmission": ("触发重传", "warning"),
    "decode_rejected": ("受损帧已拦截", "warning"),
    "application_received": ("应用消息送达", "success"),
    "transfer_failed": ("任务失败", "danger"),
    "timeout": ("确认等待超时", "warning"),
}


def event_description(event):
    d = event.details
    if event.kind == "generated":
        return f"{d['src']} → {d['dst']} · {d['app_type']} · {d['fragments']} 个分片"
    if event.kind == "mode_changed":
        return f"{d['lane']} · {d['old']} → {d['new']}"
    if event.kind == "channel_changed":
        return f"噪声标准差调整为 {d['noise']:.2f}"
    if event.kind == "application_received":
        return f"{d['src']} → {d['dst']} · {d['app_type']} · {d['body_bytes']} B"
    if event.kind == "preview_available":
        return f"{d['image_id']} · {d['bytes']} B · 接收端首次可见"
    if event.kind == "image_complete":
        return f"{d['image_id']} · {d['bytes']} B · SHA-256 一致"
    if event.kind == "image_confirmed":
        return f"{d['image_id']} · 应用层回执已送达"
    if event.kind in ("retransmission", "timeout"):
        return f"消息 {d.get('message_id')} · 序号 {d.get('sequence')}"
    return str(d.get("reason", d.get("image_id", "")))


def timeline_html(net, limit=6):
    events = [e for e in net.events if e.kind in EVENT_LABELS][-limit:]
    if not events:
        return '<div class="empty-timeline">启动场景后，关键通信事件将在这里出现。</div>'
    rows = []
    for e in reversed(events):
        title, tone = EVENT_LABELS[e.kind]
        rows.append(f'<div class="event-row"><span class="event-dot {tone}"></span>'
                    f'<div><b>{escape(title)}</b><p>{escape(event_description(e))}</p></div>'
                    f'<time>{e.time:.2f}s</time></div>')
    return '<div class="event-list">'+"".join(rows)+'</div>'


def topology_html(net, compact=False):
    from rescuelink.star_view import topology_html as draw_star
    return draw_star(net, compact)
