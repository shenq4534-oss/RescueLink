"""Read-only topology; reception is gated by the actual arrival callback."""
from html import escape
from math import hypot

INK = "#293f55"
MUTED = "#718096"
BLUE = "#326ea5"
GREEN = "#32836b"
AMBER = "#ad7d35"

LABELS = {
    "idle": "空闲",
    "sending": "发送中",
    "propagating": "传播中",
    "pending": "等待接收事件",
    "received": "已校验",
    "rejected": "校验失败",
    "stopped": "已停止",
}
HOSTS = {
    1: (100, 86, "A", "状态终端"),
    2: (100, 266, "B", "图像终端"),
    3: (700, 86, "C", "救援终端"),
    4: (700, 266, "D", "指挥中心"),
}


def attempt_phase(attempt, now, closed=False):
    if attempt.get("arrived", False):
        return "received" if attempt["ok"] else "rejected"
    if closed:
        return "stopped"
    if now < attempt["end"]:
        return "sending"
    if now < attempt["arrival"]:
        return "propagating"
    return "pending"


def star_snapshot(net):
    lanes = {}
    for lane, link in net.links.items():
        records = [
            a for a in net.attempts
            if a["lane"] == lane and a["start"] <= net.now
        ]
        pending = [a for a in records if not a.get("arrived", False)]
        last = pending[0] if pending else records[-1] if records else None
        lanes[lane] = dict(
            calls=link.calls,
            queued=len(net.queues[lane]),
            attempt=last,
            phase=attempt_phase(last, net.now, net.closed) if last else "idle",
            valid=sum(a.get("arrived", False) and a["ok"] for a in records),
            rejected=sum(
                a.get("arrived", False) and not a["ok"] for a in records
            ),
        )
    return dict(
        time=net.now,
        lanes=lanes,
        calls=sum(link.calls for link in net.links.values()),
        delivered=sum(len(host.received) for host in net.hosts.values()),
        forwards=[e for e in net.events if e.kind == "switch_forward"],
    )


def _text(x, y, content, size=12, color=INK, anchor="middle", bold=False):
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
        f'fill="{color}" font-weight="{600 if bold else 400}">'
        f'{escape(str(content))}</text>'
    )


def _computer(x, y):
    return (
        f'<g transform="translate({x-40} {y-31})" stroke="{INK}" '
        'stroke-width="1.5" stroke-linejoin="round" fill="white">'
        '<rect width="66" height="43" rx="2"/>'
        '<rect x="5" y="5" width="56" height="31" '
        'fill="#edf3f8" stroke="#9bafc2"/>'
        '<path d="M28 43v9h-9m19-9v9h9M11 57h45l6 7H5Z" '
        'fill="#f3f6f9"/>'
        '<rect x="70" y="17" width="16" height="47" rx="1" fill="#e7edf3"/>'
        '<path d="M74 24h8m-8 5h8" stroke="#9bafc2"/>'
        '<circle cx="78" cy="56" r="1.5" fill="#9bafc2" stroke="none"/>'
        '</g>'
    )


def topology_html(net, compact=False):
    snap = star_snapshot(net)
    drawing = []

    for addr, (x, y, letter, title) in HOSTS.items():
        left = addr <= 2
        p = (x+46, y+9) if left else (x-40, y+9)
        q = (
            (324, 166 if y < 180 else 192)
            if left else (476, 166 if y < 180 else 192)
        )

        drawing.append(
            f'<path d="M{p[0]} {p[1]}L{q[0]} {q[1]}" fill="none" '
            'stroke="#b9c5cf" stroke-width="1.5"/>'
        )

        live = [
            (lane, snap["lanes"][lane])
            for lane in (f"up{addr}", f"down{addr}")
            if snap["lanes"][lane]["phase"]
            in ("sending", "propagating", "pending")
        ]

        for lane, row in live:
            a = row["attempt"]
            color = (
                BLUE if a["frame_type"] == "DATA"
                else GREEN if a["frame_type"] == "ACK" else AMBER
            )
            start, end = (p, q) if lane.startswith("up") else (q, p)
            dx, dy = end[0]-start[0], end[1]-start[1]
            length = hypot(dx, dy)
            ox, oy = -dy/length*3, dx/length*3
            sx, sy = start[0]+ox, start[1]+oy
            ex, ey = end[0]+ox, end[1]+oy
            dash = (
                'stroke-dasharray="5 4"'
                if row["phase"] != "sending" else ""
            )
            drawing.append(
                f'<path d="M{sx:.1f} {sy:.1f}L{ex:.1f} {ey:.1f}" '
                f'fill="none" stroke="{color}" stroke-width="2.2" {dash}/>'
            )

            # A fixed arrow indicates direction, not an invented packet speed.
            mx, my = sx+dx*.58, sy+dy*.58
            ux, uy = dx/length, dy/length
            drawing.append(
                f'<path d="M{mx-ux*6-uy*3:.1f} {my-uy*6+ux*3:.1f}'
                f'L{mx:.1f} {my:.1f}'
                f'L{mx-ux*6+uy*3:.1f} {my-uy*6-ux*3:.1f}" '
                f'fill="none" stroke="{color}" stroke-width="2"/>'
            )

        lx, ly = (p[0]+q[0])/2, (p[1]+q[1])/2
        drawing.append(
            _text(lx, ly+(-15 if y < 180 else 24), f"P{addr}", 11, MUTED)
        )
        drawing.append(_computer(x, y))
        drawing.append(_text(x, y+53, f"{letter} · {title}", 15, bold=True))
        drawing.append(_text(x, y+72, f"ADDR {addr:02d}", 11, MUTED))

        up = snap["lanes"][f"up{addr}"]
        down = snap["lanes"][f"down{addr}"]
        drawing.append(_text(
            x, y+90,
            f'↑ {up["calls"]}   ↓ {down["calls"]}   出口排队 {down["queued"]}',
            11, MUTED
        ))

        for offset, (lane, row) in enumerate(live):
            a = row["attempt"]
            direction = "↑" if lane.startswith("up") else "↓"
            color = (
                BLUE if a["frame_type"] == "DATA"
                else GREEN if a["frame_type"] == "ACK" else AMBER
            )
            drawing.append(_text(
                lx, ly+(20 if y < 180 else 42)+offset*14,
                f'{direction} {a["frame_type"]} · {LABELS[row["phase"]]}',
                10, color
            ))

    drawing.append(
        f'<g stroke="{INK}" stroke-width="1.5" stroke-linejoin="round">'
        '<path d="M324 166l15-17h152l-15 17Z" fill="#f0f4f8"/>'
        '<path d="M476 166l15-17v32l-15 17Z" fill="#d5e0ea"/>'
        '<rect x="324" y="166" width="152" height="32" fill="#e3ebf3"/>'
        '<path d="M344 156h29m-5-3 5 3-5 3m78 0h-29m5-3-5 3 5 3"/>'
        + "".join(
            f'<rect x="{x}" y="177" width="13" height="8" fill="white"/>'
            for x in (340, 364, 388, 412)
        )
        + '<circle cx="456" cy="181" r="2" fill="#8ca7ba" stroke="none"/>'
        '</g>'
    )
    drawing.append(_text(400, 225, "中央交换机", 16, bold=True))
    drawing.append(_text(400, 247, "目的地址 → 出口端口", 12, MUTED))
    drawing.append(
        _text(400, 267, "01→P1   02→P2   03→P3   04→P4", 11, MUTED)
    )

    drawing.append('<path d="M34 385h732" stroke="#e4e9ee"/>')
    for x, color, label in (
        (42, BLUE, "DATA"),
        (133, GREEN, "ACK"),
        (217, AMBER, "其他控制帧"),
    ):
        drawing.append(
            f'<path d="M{x} 407h18" stroke="{color}" stroke-width="2.2"/>'
        )
        drawing.append(_text(x+25, 411, label, 11, MUTED, "start"))

    drawing.append(_text(
        766, 411,
        f'Cable 调用 {snap["calls"]}  ·  应用送达 {snap["delivered"]}',
        11, MUTED, "end"
    ))
    drawing.append(_text(
        400, 434,
        "实线：发送中；虚线：传播或等待接收事件。↑/↓ 为主机上行/下行调用次数。",
        10, MUTED
    ))

    return (
        '<div class="topology textbook-star" '
        'style="background:white;border-radius:0">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" '
        'role="img" aria-label="四主机星形网络：四条双向连接，八个独立方向 Cable" '
        f'style="width:100%;height:auto;max-height:{300 if compact else 430}px;'
        'display:block;font-family:Times New Roman,SimSun,Songti SC,'
        'Noto Serif CJK SC,serif">'
        '<rect width="800" height="450" fill="white"/>'
        + "".join(drawing) + '</svg></div>'
    )


def render_details(net):
    import streamlit as st
    snap = star_snapshot(net)

    with st.expander("转发证据 · 地址、队列与两跳 Cable"):
        st.caption(
            "图只读事件状态；接收回调执行后才显示校验结果。"
            "地址是协议地址，不是 IP。"
        )
        st.dataframe([
            dict(
                方向=lane,
                状态=LABELS[row["phase"]],
                Cable调用=row["calls"],
                等待发送=row["queued"],
                已校验=row["valid"],
                拒收=row["rejected"],
            )
            for lane, row in snap["lanes"].items()
        ], hide_index=True, width="stretch")

        events = snap["forwards"][-8:]
        if events:
            st.dataframe([
                dict(
                    接收时刻=e.time,
                    入方向=e.details["ingress"],
                    出方向=e.details["egress"],
                    类型=e.details["frame_type"],
                    消息=e.details["message_id"],
                    序号=e.details["sequence"],
                    接收帧SHA256=e.details["frame_sha256"],
                )
                for e in events
            ], hide_index=True, width="stretch")
        else:
            st.info("交换机尚未接收并转发有效帧。先单步推进。")

        st.caption(
            "发送耗时、传播耗时与队列等待来自模拟时钟。"
            "当前模型没有单独的交换机处理时延；"
            "process_delay 是目的主机消费分片的时延。"
        )

    with st.expander("逐帧比特与波形 · 原版 Cable 的真实记录"):
        from rescuelink.ui.inspector import network_inspector
        network_inspector(net)
