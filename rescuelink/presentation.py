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
    """Highlight frames whose actual virtual transmission interval includes now."""
    active = {}
    for a in net.attempts:
        if a["start"] <= net.now < a["end"]:
            active[a["lane"]] = a
    nodes = {1: (38, 33, "A", "状态终端", "STATUS"),
             2: (38, 202, "B", "图像终端", "IMAGING"),
             3: (548, 33, "C", "救援终端", "SOS"),
             4: (548, 202, "D", "指挥中心", "COMMAND")}
    lines, cards = [], []
    for addr, (x, y, name, title, subtitle) in nodes.items():
        left = addr <= 2
        x1, y1, x2, y2 = (x+174, y+42, 316, 160) if left else (444, 160, x, y+42)
        lanes = [f"up{addr}", f"down{addr}"]
        selected = next((active[k] for k in lanes if k in active), None)
        color = "#c95939" if selected and selected["frame_type"] == "DATA" else "#2e7964" if selected else "#cfd6cf"
        lines.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="{3 if selected else 1.5}"/>')
        if selected:
            lane = selected["lane"]
            up = lane.startswith("up")
            start = (x1,y1) if left == up else (x2,y2)
            end = (x2,y2) if left == up else (x1,y1)
            fraction = min(1, max(0, (net.now-selected["start"])/(selected["end"]-selected["start"])))
            px=start[0]+(end[0]-start[0])*fraction
            py=start[1]+(end[1]-start[1])*fraction
            lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{color}"/>')
        queued = sum(len(net.queues[k]) for k in lanes)
        mode=net.controllers[f"down{addr}"].mode
        status="已停止" if net.closed else "传输中" if selected else f"排队 {queued}" if queued else "就绪"
        cards.append(f'<g><rect x="{x}" y="{y}" width="174" height="84" rx="10" fill="white" stroke="{color}"/>'
                     f'<rect x="{x+12}" y="{y+14}" width="28" height="28" rx="7" fill="#f0f3ed"/>'
                     f'<text x="{x+26}" y="{y+34}" text-anchor="middle" fill="#355b4c" font-size="15" font-weight="700">{name}</text>'
                     f'<text x="{x+50}" y="{y+27}" font-size="14" font-weight="600" fill="#243d32">{title}</text>'
                     f'<text x="{x+50}" y="{y+43}" font-size="9" letter-spacing="1" fill="#85918a">{subtitle}</text>'
                     f'<circle cx="{x+18}" cy="{y+65}" r="3" fill="{color if selected else "#6f9a78"}"/>'
                     f'<text x="{x+28}" y="{y+69}" font-size="11" fill="#718177">{status}</text>'
                     f'<text x="{x+158}" y="{y+69}" text-anchor="end" font-size="10" fill="#85918a">{mode}</text></g>')
    count=sum(l.calls for l in net.links.values())
    center=(f'<rect x="316" y="117" width="128" height="88" rx="12" fill="#254e40"/>'
            '<g stroke="#a5c4ad" stroke-width="1.5"><path d="M361 143h38m-5-5 5 5-5 5M399 157h-38m5-5-5 5 5 5"/></g>'
            '<text x="380" y="180" text-anchor="middle" fill="white" font-size="14" font-weight="600">中央交换机</text>'
            '<text x="380" y="194" text-anchor="middle" fill="#b8d0bf" font-size="9">ADDRESS → PORT</text>'
            f'<text x="380" y="238" text-anchor="middle" fill="#819085" font-size="10">{count} 次真实 Cable 调用</text>')
    return ('<div class="topology"><svg viewBox="0 0 760 313" role="img" aria-label="四主机星形网络实时状态">'
            '<defs><pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse">'
            '<circle cx="1" cy="1" r="0.65" fill="#dce1d8"/></pattern></defs>'
            '<rect width="760" height="313" fill="url(#dots)"/>'
            '<g fill="none">'+''.join(lines)+'</g>'+''.join(cards)+center+'</svg></div>')
