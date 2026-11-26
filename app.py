"""Run: streamlit run app.py. UI advances the real engine in bounded steps."""
from pathlib import Path
import json
import streamlit as st
import plotly.graph_objects as go
from rescuelink.config import Config, HOSTS
from rescuelink.network.engine import Network
from rescuelink.protocol.application import Message
from rescuelink.media.image_transfer import demo_image
from rescuelink.simulation.scenarios import configure_showcase
from rescuelink.simulation.metrics import network_metrics
from rescuelink.ui.inspector import point_to_point_lab, network_inspector

st.set_page_config(page_title="RescueLink · 应急通信",page_icon="📡",layout="wide")
st.markdown("""<style>.stApp{background:#0c1823}h1,h2,h3{letter-spacing:.02em}
[data-testid=stMetric]{background:#142937;padding:16px;border-radius:12px}
.block-container{padding-top:2rem}</style>""",unsafe_allow_html=True)
st.title("RescueLink")
st.caption("自适应可靠应急通信网络 · 4 Hosts / 1 Switch / 8 directed Cables")
view=st.radio("演示视图",["应急网络","底层实验室"],horizontal=True)

with st.sidebar:
    st.subheader("新场景配置")
    noise=st.slider("噪声标准差",0.0,2.0,.15,.05)
    policy=st.selectbox("通信保护",["Auto","Fixed Fast","Fixed Balanced","Fixed Survival"])
    modulation=st.selectbox("调制",["BPSK","ASK","BFSK"])
    st.caption("Fast 无 FEC；Balanced / Survival 使用 Hamming(8,4)，PHY 头固定保护。")
    scheduling=st.selectbox("交换机调度",["Priority","FIFO"])
    transport=st.selectbox("可靠传输",["GBN","Stop-and-Wait"])
    window=st.slider("发送窗口",1,16,8)
    slowdown=st.slider("下行符号时长倍率（形成拥塞）",1,4,2)
    seed=st.number_input("随机种子",min_value=0,max_value=100000,value=42)
    st.caption("修改后点击“应用配置 / 重置”。所有时间均为模拟秒。")

if view=="底层实验室":
    # Preserve the network snapshot while inspecting a separate point-to-point link.
    st.session_state.playing=False
    point_to_point_lab(noise,modulation,int(seed))
    st.stop()

def new_network():
    if "net" in st.session_state:
        st.session_state.net.close()
    st.session_state.net=Network(Config(seed=int(seed),noise=noise,policy=policy,scheduler=scheduling,
        transport=transport,window=window,downlink_slowdown=slowdown,modulation=modulation),"outputs/ui_received",capture=True)
    st.session_state.playing=False
    st.session_state.counter=0

if "net" not in st.session_state:
    new_network()
net=st.session_state.net

c1,c2,c3,c4=st.columns(4)
if c1.button("应用配置 / 重置",use_container_width=True):
    new_network(); st.rerun()
if c2.button("运行完整 Demo",use_container_width=True):
    new_network(); net=st.session_state.net
    configure_showcase(net)
    st.session_state.playing=True
if c3.button("暂停 / 继续",use_container_width=True):
    st.session_state.playing=not st.session_state.playing
if c4.button("停止任务",use_container_width=True):
    net.close(); st.session_state.playing=False
    st.info("已停止并关闭链路线程；重置可重新发送。")

st.markdown('''<svg viewBox="0 0 1000 175" role="img" aria-label="四主机星型网络" style="width:100%;max-height:175px">
<g stroke="#3b9b9a" stroke-width="2"><path d="M190 42L450 87M190 132L450 87M550 87L810 42M550 87L810 132"/></g>
<g fill="#142937" stroke="#3b9b9a"><rect x="15" y="15" width="175" height="52" rx="10"/><rect x="15" y="107" width="175" height="52" rx="10"/>
<rect x="450" y="58" width="100" height="58" rx="10"/><rect x="810" y="15" width="175" height="52" rx="10"/><rect x="810" y="107" width="175" height="52" rx="10"/></g>
<g fill="#e4edf2" font-size="17" text-anchor="middle"><text x="103" y="47">A · 状态终端</text><text x="103" y="139">B · 图片终端</text>
<text x="500" y="94">Switch</text><text x="898" y="47">C · SOS</text><text x="898" y="139">D · 指挥中心</text></g>
<g fill="#7fb6b5" font-size="12" text-anchor="middle"><text x="305" y="41">up1 / down1 Cable</text><text x="305" y="146">up2 / down2 Cable</text>
<text x="695" y="41">up3 / down3 Cable</text><text x="695" y="146">up4 / down4 Cable</text></g></svg>''',unsafe_allow_html=True)
st.caption("所有终端只连接中央 Switch；图中每个连接包含独立上行和下行。")

with st.container(border=True):
    a,b=st.columns(2)
    with a:
        src=st.selectbox("发送方",list(HOSTS),format_func=HOSTS.get,index=0)
        dst=st.selectbox("接收方",list(HOSTS),format_func=HOSTS.get,index=3)
        text=st.text_area("UTF-8 文本","现场状态正常，等待指挥。")
        if st.button("发送文本",disabled=net.closed):
            st.session_state.counter+=1
            net.send(src,dst,Message("TEXT",f"text-{st.session_state.counter}",{},text.encode()))
            st.session_state.playing=True
        if st.button("查询状态",disabled=net.closed):
            st.session_state.counter+=1
            net.send(src,dst,Message("STATUS_QUERY",f"status-{st.session_state.counter}",{}))
            st.session_state.playing=True
    with b:
        upload=st.file_uploader("PNG / JPEG（≤512 KiB，≤400 万像素）",type=["png","jpg","jpeg"])
        progressive=st.checkbox("预览优先（取消则仅发原图）",value=True)
        if st.button("开始图片上传",disabled=net.closed):
            try:
                net.start_image(2,4,upload.getvalue() if upload else demo_image(),progressive)
                # Pause deliberately after submission, so the user can step or trigger SOS.
                st.session_state.playing=False
                st.info("已提交 B→D 图片；点击继续或单步，让预览和原图逐步到达。")
            except ValueError as exc:
                st.error(str(exc))
        if st.button("触发 SOS",type="primary",disabled=net.closed):
            st.session_state.counter+=1
            net.send(3,4,Message("SOS_ALERT",f"sos-{st.session_state.counter}",{},"SOS：四区需要救援！".encode()),0)
            st.session_state.playing=True
        if st.button("单步推进 12 个事件",disabled=net.closed):
            net.step(12)

@st.fragment(run_every="500ms")
def monitor():
    n=st.session_state.net
    if st.session_state.playing and not n.closed:
        try:
            if not n.step(12): st.session_state.playing=False
        except Exception as exc:
            st.session_state.playing=False
            st.error(f"运行失败，状态已保留：{exc}")
    s=network_metrics(n)
    cols=st.columns(5)
    cols[0].metric("模拟时间",f"{n.now:.3f} s")
    cols[1].metric("应用送达 / 生成",f"{s['delivered']} / {s['generated']}")
    cols[2].metric("有效吞吐",f"{s['goodput_bps']:.1f} bit/s")
    cols[3].metric("重传 / 损坏帧",f"{s.get('retransmissions',0)} / {s.get('damaged_frames',0)}")
    cols[4].metric("Hamming 纠正码字",s.get("corrected_codewords",0))
    receive,tech,wire,charts=st.tabs(["接收端", "链路与事件", "逐帧追踪", "已计算实验"])
    with receive:
        st.caption("以下内容只来自解调、CRC、分片重组通过后的接收字节。")
        for addr,host in n.hosts.items():
            if host.received or host.images:
                st.markdown(f"**{HOSTS[addr]}**")
            for (source,iid),im in host.images.items():
                left,right=st.columns(2)
                with left:
                    if im["preview"] is not None:
                        st.image(im["preview"],caption=f"网络收到预览 · T={im['preview_time']:.3f}s",width=260)
                    else: st.info(f"{iid} · 等待预览 / 原图")
                with right:
                    if im["verified"]:
                        st.image(im["original"],caption=f"原图完成 · T={im['full_time']:.3f}s",width=320)
                        st.success("SHA-256 一致")
                        st.code(im["meta"]["sha256"])
                    else:
                        failed=any(f.status=="failed" and f.request_id==iid for f in n.flows.values())
                        st.warning("传输失败，保留已收到预览" if failed else "原图传输中；完整校验后显示")
            rows=[]
            for r in host.received[-20:]:
                m=r["message"]
                rows.append(dict(time=round(r["time"],4),src=r["src"],dst=r["dst"],type=m.type,
                    request=m.request_id,bytes=len(m.body),content=m.body.decode("utf-8",errors="replace")[:140] if not m.type.startswith("IMAGE_") else json.dumps(m.meta,ensure_ascii=False)))
            if rows: st.dataframe(rows,use_container_width=True,hide_index=True)
        for f in n.flows.values():
            if f.status in ("failed","cancelled"):
                st.error(f"消息 {f.message_id} ({f.app_type})：{f.status}")
    with tech:
        st.dataframe([dict(lane=lane,mode=c.mode,recent=list(c.recent),queued=len(n.queues[lane]),
            physical_calls=n.links[lane].calls) for lane,c in n.controllers.items()],hide_index=True)
        st.caption(f"DATA={s.get('DATA',0)}  ACK={s.get('ACK',0)}  NACK={s.get('NACK',0)}  不可纠正={s.get('detected_uncorrectable',0)}")
        if s["sos_latencies"]: st.write("SOS 端到端时延（秒）",s["sos_latencies"])
        changes=[e.asdict() for e in n.events if e.kind=="mode_changed"]
        if changes: st.dataframe(changes,hide_index=True)
        link=next((l for l in reversed(list(n.links.values())) if l.last),None)
        if link:
            fig=go.Figure()
            fig.add_scatter(y=link.last["tx"],name="TX")
            fig.add_scatter(y=link.last["rx"],name="RX",opacity=.65)
            fig.update_layout(height=250,title=f"真实波形片段 · {link.name}",margin=dict(t=40,b=20))
            st.plotly_chart(fig,use_container_width=True)
        important=[e.asdict() for e in n.events if e.kind not in ("link_feedback","window_advertised")]
        st.dataframe([dict(time=round(e["time"],4),kind=e["kind"],details=json.dumps({k:v for k,v in e.items() if k not in ("time","kind")},ensure_ascii=False)) for e in important[-100:]],hide_index=True)
        st.download_button("下载当前真实事件日志","\n".join(json.dumps(e.asdict(),ensure_ascii=False) for e in n.events),"events.jsonl")
    with wire:
        network_inspector(n)
    with charts:
        p=Path("outputs/experiments/results.json")
        if p.exists():
            results=json.loads(p.read_text(encoding="utf-8"))
            st.caption(f"离线实测 · {results['generated_utc']} · quick={results['quick']} · 种子见 JSON")
            for filename in ("e2_shannon.png","e3_modulations.png","e4_coding.png","adaptive.png","scheduling.png"):
                if (p.parent/filename).exists(): st.image(str(p.parent/filename))
        else: st.info("先运行 python experiments/run_all.py --quick 生成图表。")

monitor()
