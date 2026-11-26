"""Streamlit views for the recording console; protocol logic lives elsewhere."""
from html import escape
import json
import plotly.graph_objects as go
import streamlit as st
from rescuelink.config import HOSTS
from rescuelink.presentation import fmt, image_snapshot

def html(content):
    st.markdown(content, unsafe_allow_html=True)

def heading(title, detail=''):
    html(f'<div class="section-head"><h3>{escape(title)}</h3><span>{escape(detail)}</span></div>')

def waveform(link, payload=True):
    last = link.last if link else None
    if not last:
        st.caption('发送一帧后，这里显示原版 Cable 前后的真实采样波形。')
        return
    key = '_payload' if payload else ''
    tx, rx = (last.get('tx' + key, last['tx']), last.get('rx' + key, last['rx']))
    fig = go.Figure()
    fig.add_scatter(y=rx[:160], name='RX · 接收', line=dict(color='#d1a479', width=1.2), opacity=0.8)
    fig.add_scatter(y=tx[:160], name='TX · 发送', line=dict(color='#3d7560', width=1.5))
    fig.update_layout(height=195, margin=dict(t=8, b=28, l=30, r=8), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Noto Sans CJK SC, sans-serif', size=10, color='#82917d'), legend=dict(orientation='h', y=1.2, x=0, font=dict(size=10)), xaxis=dict(title='采样点', showgrid=False, zeroline=False), yaxis=dict(showgrid=True, gridcolor='#e7ebdf', zeroline=False))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

def metrics(net, s):
    rows = [('模拟时钟', fmt(net.now, 2), 's', '播放速度不改变网络时间'), ('应用消息送达', f"{s['delivered']} / {s['generated']}", '', f"含请求与应用响应 · 失败 {s['failed']}"), ('有效吞吐率', fmt(s['goodput_bps']), 'bit/s', '唯一应用载荷 / 模拟时间'), ('可靠恢复', str(s.get('retransmissions', 0)), '次重传', f"检测受损帧 {s.get('damaged_frames', 0)}"), ('Hamming 纠错', f"{s.get('corrected_codewords', 0):,}", '码字', f"不可纠正 {s.get('detected_uncorrectable', 0)}")]
    html('<div class="metric-grid">' + ''.join((f'<div class="metric-cell"><div class="metric-label">{label}</div><div class="metric-value">{value}<em>{unit}</em></div><div class="metric-note">{note}</div></div>' for label, value, unit, note in rows)) + '</div>')

def receiver(net):
    snap = image_snapshot(net)
    heading('指挥中心 · 接收画面', 'D / NETWORK RECEIVED')
    pixels = snap['original'] if snap['original'] is not None else snap['preview']
    if pixels is None:
        html(f"""<div class="empty-receiver"><svg width="42" height="38" viewBox="0 0 42 38" fill="none"><rect x="2" y="2" width="38" height="32" rx="5" stroke="#899b7b" stroke-width="1.4"/><path d="m5 29 10-11 7 6 7-10 10 15" stroke="#899b7b" stroke-width="1.4"/><circle cx="13" cy="11" r="3" stroke="#899b7b"/></svg><strong>{snap['label']}</strong><p>预览先到达，原图随后校验<br>仅显示从信道恢复的接收字节</p></div>""")
    else:
        st.image(pixels, width='stretch')
    html(f"""<div class="receiver-status"><span>{escape(snap['label'])}</span><span>{snap['acked']} / {snap['fragments']} 原图分片已确认</span></div>""")
    st.progress(snap['progress'])
    if snap['image']:
        im = snap['image']
        html(f"""<div class="network-foot"><span>预览可用 {fmt(im['preview_time'], 2, 's')}</span><span>原图完成 {fmt(im['full_time'], 2, 's')}</span></div>""")
        if im['verified']:
            html(f"""<div class="hash">✓ SHA-256 一致<br>{escape(im['meta']['sha256'])}</div>""")
            st.download_button('下载实际接收的原图', im['original'], f"{snap['image_id']}.{im['meta']['format'].lower()}", width='stretch')

def inbox(net, limit=3):
    heading('消息与救援回执', 'APPLICATION INBOX')
    messages = sorted([r for h in net.hosts.values() for r in h.received if not r['message'].type.startswith('IMAGE_') and r['message'].type != 'READY'], key=lambda r: r['time'], reverse=True)[:limit]
    if not messages:
        html('<div class="empty-timeline">等待文本、状态响应或 SOS 回执。</div>')
    for r in messages:
        m = r['message']
        body = m.body.decode('utf-8', errors='replace') if m.body else json.dumps(m.meta, ensure_ascii=False)
        html(f"""<div class="message-card {('sos' if m.type.startswith('SOS') else '')}"><div class="message-meta"><span>{r['src']} → {r['dst']} / {escape(m.type)}</span><span>{r['time']:.2f}s</span></div><div class="message-body">{escape(body[:180])}</div></div>""")

def diagnostics(net, s, expanded=False):
    with st.expander('链路详情 · 帧头、真实波形与事件日志', expanded=expanded):
        left, right = st.columns([1, 1.2], gap='large')
        with left:
            heading('地址 → 出口', 'STATIC FORWARDING')
            st.dataframe([dict(主机=HOSTS[a], 地址=a, 出口=f'P{a}', 上行调用=net.links[f'up{a}'].calls, 下行调用=net.links[f'down{a}'].calls, 出口排队=len(net.queues[f'down{a}'])) for a in HOSTS], hide_index=True, width='stretch')
            st.caption('每次 DATA、ACK、反馈和应用响应都经过实际 Cable。')
        with right:
            lane = st.selectbox('波形链路', list(net.links), index=7)
            area = st.radio('波形位置', ['数据载荷', '前导序列'], horizontal=True)
            waveform(net.links[lane], payload=area == '数据载荷')
        if net.attempts:
            heading('最近发送的真实帧', 'NOT A PRESET PACKET')
            a = net.attempts[-1]
            fields = {'lane': a['lane'], 'type': a['frame_type'], 'src': a['src'], 'dst': a['dst'], 'message_id': a['message_id'], 'sequence': a['sequence'], 'frame_bytes': a['frame_bytes'], 'mode': a['mode'], 'CRC/FEC': ('通过' if a['ok'] else a['error']) if a.get('arrived', False) else '等待接收事件'}
            st.code(json.dumps(fields, ensure_ascii=False), language='json')
        changes = [e.asdict() for e in net.events if e.kind == 'mode_changed']
        if changes:
            st.caption('保护模式变化来自真实链路反馈或 ACK 超时。')
            st.dataframe(changes, hide_index=True, width='stretch')
        important = [e.asdict() for e in net.events if e.kind not in ('link_feedback', 'window_advertised')]
        if important:
            st.dataframe([dict(模拟秒=round(e['time'], 3), 事件=e['kind'], 详情=json.dumps({k: v for k, v in e.items() if k not in ('time', 'kind')}, ensure_ascii=False)) for e in important[-60:]], hide_index=True, width='stretch', height=240)
        st.download_button('下载当前真实事件日志', '\n'.join((json.dumps(e.asdict(), ensure_ascii=False) for e in net.events)), 'rescuelink_events.jsonl', mime='application/x-ndjson')
        st.download_button('下载本次指标与配置', json.dumps(s, ensure_ascii=False, indent=2), 'rescuelink_summary.json', mime='application/json')

@st.fragment(run_every='500ms')
def point_monitor():
    p = st.session_state.get('p2p')
    if p and st.session_state.get('p2p_playing'):
        if not p.step():
            st.session_state.p2p_playing = False
    html('<div class="pipeline"><div>UTF-8 / 分片<small>BYTES → BITS</small></div><div>调制<small>MODULATION</small></div><div>原版 Cable<small>ATTENUATION + NOISE</small></div><div>解调 / CRC<small>RECOVERY + CHECK</small></div><div>重组<small>BYTES → TEXT</small></div></div>')
    if not p:
        st.info('点击开始，将逐个分片通过真实 Cable 发送；也可暂停后单步录制。')
        return
    a, b = st.columns([1.35, 1], gap='medium')
    with a:
        with st.container(border=True):
            heading('分片发送与检错', f'{len(p.data):,} B / {len(p.parts)} FRAGMENTS')
            chips = []
            for i in range(len(p.parts)):
                state = 'ok' if i < len(p.records) and p.records[i]['ok'] else 'bad' if i < len(p.records) else ''
                chips.append(f'<span class="fragment-chip {state}">{i:02d}</span>')
            html('<div class="fragment-grid">' + ''.join(chips) + '</div>')
            st.progress(len(p.records) / len(p.parts))
            ok = sum((r['ok'] for r in p.records))
            st.caption(f'CRC / FEC 通过 {ok} · 拒绝 {len(p.records) - ok} · Cable 调用 {p.link.calls} · 模拟时间 {p.now:.3f}s')
            heading('真实载荷波形', p.config.modulation)
            waveform(p.link)
    with b:
        with st.container(border=True):
            heading('B · 恢复后的接收文本', 'RECEIVER')
            if p.received is not None:
                st.success('字节完全一致' if p.success else '已收到完整消息')
                st.text_area('恢复文本', p.received.decode('utf-8', errors='replace'), height=180, disabled=True)
                st.caption(f'有效速率 {len(p.received) * 8 / p.now:.1f} bit/s')
            elif p.done:
                st.error('消息不完整：至少一片未通过检错。当前 Level 1 不进行重传。')
            else:
                html('<div class="empty-receiver"><strong>接收端正在等待完整消息</strong><p>不提前显示原始文本<br>分片全部恢复后再执行 UTF-8 解码</p></div>')
            heading('发送端前 64 个数据比特')
            html(f"""<div class="bit-preview">{escape(' '.join((f'{v:08b}' for v in p.data[:8])))}</div>""")
    if p.records:
        with st.expander('逐片检错记录与实验导出'):
            st.dataframe([dict(序号=r['index'], 载荷字节=r['payload_bytes'], 校验='通过' if r['ok'] else r['error'], 原始误码=r['raw_errors'], 纠正码字=r['corrected_codewords'], 到达秒=round(r['arrival'], 4)) for r in p.records], hide_index=True, width='stretch')
            st.download_button('下载点对点实测记录', json.dumps(dict(success=p.success, fragments=len(p.parts), simulated_seconds=p.now, records=p.records), ensure_ascii=False, indent=2), 'level1_recording.json', mime='application/json')
