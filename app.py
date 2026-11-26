"""RescueLink recording console. Run: python -m streamlit run app.py."""
from html import escape
from pathlib import Path
import json
import streamlit as st
from rescuelink.config import Config, HOSTS
from rescuelink.console_views import html, heading, metrics, receiver, inbox, diagnostics, point_monitor
from rescuelink.presentation import PointToPointSession, advance, timeline_html, topology_html
from rescuelink.network.engine import Network
from rescuelink.protocol.application import Message
from rescuelink.media.image_transfer import demo_image
from rescuelink.simulation.scenarios import configure_showcase
from rescuelink.simulation.metrics import network_metrics

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="RescueLink · 应急通信指挥台",page_icon="📡",layout="wide",initial_sidebar_state="collapsed")
html('<style>'+ (ROOT/'assets/console.css').read_text(encoding='utf-8')+'</style>')

with st.sidebar:
    st.markdown('### 场景配置')
    st.caption('配置在重置后生效；即时干扰按钮直接作用于当前网络。')
    noise=st.slider('噪声标准差',0.0,2.0,.15,.05)
    policy=st.selectbox('通信保护',['Auto','Fixed Fast','Fixed Balanced','Fixed Survival'])
    modulation=st.selectbox('调制',['BPSK','ASK','BFSK'])
    scheduling=st.selectbox('交换机调度',['Priority','FIFO'])
    transport=st.selectbox('可靠传输',['GBN','Stop-and-Wait'])
    window=st.slider('发送窗口',1,16,8)
    slowdown=st.slider('下行符号时长倍率（形成拥塞）',1,4,2)
    seed=st.number_input('随机种子',min_value=0,max_value=100000,value=42)
    st.caption('Fast 无载荷 FEC；Balanced / Survival 使用 Hamming(8,4)。固定 PHY 头始终保护。')
    st.divider()
    speed=st.select_slider('播放速度',options=[4,12,32,64],value=12,
        format_func=lambda x:{4:'讲解 · 慢速',12:'标准',32:'快速',64:'验收 · 快速完成'}[x])
    st.caption('每次刷新推进的事件数；不改变网络的模拟时延或吞吐率。')
    recording=st.toggle('录制模式',value=False)
    st.caption('减少辅助信息，保留实际结果和通信指标。')


def make_config():
    return Config(seed=int(seed),noise=noise,policy=policy,scheduler=scheduling,
        transport=transport,window=window,downlink_slowdown=slowdown,modulation=modulation)


def new_network():
    if 'net' in st.session_state:
        st.session_state.net.close()
    st.session_state.net=Network(make_config(),ROOT/'outputs/ui_received')
    st.session_state.playing=False
    st.session_state.counter=0
    st.session_state.target=None
    st.session_state.notice='场景已就绪 · 选择一个任务开始'


if 'net' not in st.session_state:
    new_network()

html('<div class="masthead"><div><div class="brandline"><span class="brandmark">+</span>'
     '<span class="wordmark">RescueLink<span style="color:#c95939">.</span></span>'
     '<span class="edition">COMMUNICATION LAB / 01</span></div>'
     '<h1>让关键信息，先一步抵达。</h1><p>自适应可靠应急通信 · 从真实波形到现场图像</p></div>'
     '<div class="header-aside"><span class="online-dot"></span>本地实验环境<br>'
     '<span class="badge">4 HOSTS / 1 SWITCH</span><br>Level 1 → Level 2 → Level 3</div></div>')
page=st.radio('展示页面',['指挥总览','Level 1 · 点对点','Level 2 · 星形转发','实验与对照'],
              horizontal=True,label_visibility='collapsed')
if recording:
    html('<style>[data-testid="stToolbarActions"],[data-testid="stAppDeployButton"]{display:none}'
         '.block-container{padding-top:1rem}.edition{display:none}'
         '.masthead{margin-bottom:.6rem}.masthead h1{margin-top:8px;font-size:26px}'
         '.metric-cell{padding-top:10px;padding-bottom:10px}.metric-value{font-size:24px}'
         '.topology svg{max-height:270px}.event-list{max-height:195px}'
         '.st-key-receiver_panel [data-testid="stImage"] img{max-height:180px;object-fit:contain}</style>')


def controls():
    net=st.session_state.net
    cols=st.columns([1.55,1,1.25,.9,1.2,.8])
    if cols[0].button('运行完整 Demo',type='primary',use_container_width=True):
        new_network()
        configure_showcase(st.session_state.net)
        st.session_state.playing=True
        st.session_state.notice='完整场景运行中 · 22s 生成 SOS / 32s 加噪 / 55s 恢复'
    net=st.session_state.net
    if cols[1].button('暂停 / 继续',disabled=net.closed,use_container_width=True):
        st.session_state.playing=not st.session_state.playing
        st.session_state.target=None
    if cols[2].button('单步推进 12 个事件',disabled=net.closed,use_container_width=True):
        st.session_state.playing=False
        st.session_state.target=None
        net.step(12)
    if cols[3].button('触发 SOS',disabled=net.closed,use_container_width=True):
        st.session_state.counter+=1
        net.send(3,4,Message('SOS_ALERT',f'sos-{st.session_state.counter}',{},'SOS：四区需要救援！'.encode()),0)
        st.session_state.playing=True
        st.session_state.notice='C → D 救援请求已提交，优先级 0'
    if cols[4].button('应用配置 / 重置',use_container_width=True):
        new_network()
        st.rerun()
    if cols[5].button('停止任务',disabled=net.closed,use_container_width=True):
        net.close()
        st.session_state.playing=False
        st.session_state.notice='任务已停止，已关闭链路线程；重置可重新开始'


@st.fragment(run_every='500ms')
def network_monitor():
    net=st.session_state.net
    if st.session_state.playing and not net.closed:
        try:
            more,reached=advance(net,speed,st.session_state.target)
            if reached:
                label={'preview':'预览已实际到达','sos':'SOS 已实际送达','image':'原图已实际校验'}[st.session_state.target]
                st.session_state.notice=label+' · 已自动暂停，可以讲解或继续'
                st.session_state.playing=False
                st.session_state.target=None
            elif not more:
                st.session_state.playing=False
                st.session_state.notice=('事件队列已结束，但未达到指定里程碑 · 请检查任务是否已提交或失败'
                                         if st.session_state.target else '事件队列已完成 · 查看实际结果或重置场景')
                st.session_state.target=None
        except Exception as exc:
            st.session_state.playing=False
            st.error(f'运行失败，状态已保留：{exc}')
    s=network_metrics(net)
    metrics(net,s)
    left,right=st.columns([1.55,1],gap='medium')
    with left:
        with st.container(border=True):
            heading('现场通信拓扑','STAR NETWORK / 8 DIRECTED CABLES')
            html(topology_html(net))
            html('<div class="network-foot"><span>静态地址转发 · 所有终端仅连接中心节点</span>'
                 '<span><i class="legend-dot" style="background:#c95939"></i>DATA'
                 '<i class="legend-dot" style="background:#2e7964"></i>控制帧</span></div>')
        with st.container(border=True):
            heading('关键事件','LIVE EVENT TIMELINE')
            html(timeline_html(net,4 if recording else 5))
    with right:
        with st.container(border=True,key='receiver_panel'):
            receiver(net)
        with st.container(border=True):
            inbox(net,2 if recording else 3)
            if s['sos_latencies']:
                html(f'<div class="notice">SOS 实际端到端时延 <b>{s["sos_latencies"][-1]:.3f}s</b> · 含发送与排队</div>')
    live_noise=next(iter(net.links.values())).cable.noise_level
    state='已停止' if net.closed else '运行中' if st.session_state.playing else '已暂停' if net.flows else '待命'
    html(f'<div class="session-strip"><span><span class="pill">{state}</span> {escape(st.session_state.notice)}</span>'
         f'<span>{net.config.modulation} / {net.config.transport} / {net.config.scheduler} · 当前 σ={live_noise:.2f}</span></div>')
    if not recording or page=='Level 2 · 星形转发':
        diagnostics(net,s,expanded=page=='Level 2 · 星形转发')


def task_controls():
    net=st.session_state.net
    with st.expander('演示控制 · 在真实接收节点暂停 / 注入信道干扰'):
        st.caption('不会跳过传输。持续处理真实事件，达到指定接收节点时才自动暂停。')
        cols=st.columns(5)
        for col,label,target in zip(cols[:3],['推进至预览到达','推进至 SOS 送达','推进至原图校验'],['preview','sos','image']):
            if col.button(label,disabled=net.closed,use_container_width=True):
                st.session_state.target=target
                st.session_state.playing=True
                st.session_state.notice='正在推进至真实里程碑：'+label
                st.rerun()
        if cols[3].button('加入干扰 σ=0.85',disabled=net.closed,use_container_width=True):
            net.set_noise(.85)
            st.session_state.notice='即时干扰已施加到实际 Cable；当前播放状态保持'
            st.rerun()
        if cols[4].button('恢复链路 σ=0.12',disabled=net.closed,use_container_width=True):
            net.set_noise(.12)
            st.session_state.notice='实际 Cable 噪声已恢复至 0.12'
            st.rerun()


def composer():
    net=st.session_state.net
    with st.expander('手动任务 · 文字 / 状态查询 / 图片上传'):
        left,right=st.columns(2,gap='large')
        with left:
            st.markdown('**发送消息**')
            a,b=st.columns(2)
            src=a.selectbox('发送方',list(HOSTS),format_func=HOSTS.get,index=0)
            dst=b.selectbox('接收方',list(HOSTS),format_func=HOSTS.get,index=3)
            text=st.text_area('UTF-8 文本','现场状态正常，等待指挥。',height=90)
            a,b=st.columns(2)
            if a.button('发送文本',disabled=net.closed,use_container_width=True):
                st.session_state.counter+=1
                net.send(src,dst,Message('TEXT',f'text-{st.session_state.counter}',{},text.encode()))
                st.session_state.playing=True
                st.rerun()
            if b.button('查询状态',disabled=net.closed,use_container_width=True):
                st.session_state.counter+=1
                net.send(src,dst,Message('STATUS_QUERY',f'status-{st.session_state.counter}',{}))
                st.session_state.playing=True
                st.rerun()
        with right:
            st.markdown('**B → D 现场图像**')
            upload=st.file_uploader('PNG / JPEG（≤512 KiB，≤400 万像素）',type=['png','jpg','jpeg'])
            progressive=st.checkbox('预览优先（取消则仅发原图）',value=True)
            if st.button('开始图片上传',disabled=net.closed,use_container_width=True):
                try:
                    net.start_image(2,4,upload.getvalue() if upload else demo_image(),progressive)
                    st.session_state.playing=False
                    st.session_state.target=None
                    st.session_state.notice='B → D 图像已提交 · 已暂停，可单步或推进至预览到达'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            st.caption('未选择文件时使用内置示例。上传后先暂停，便于逐步录制。')


def level1_view():
    st.session_state.playing=False
    html('<div class="record-hint">LEVEL 1 / UTF-8 → 分片 → 调制 → Cable → 解调 → CRC → 重组。'
         '这里是独立点对点信道，不经过交换机，也没有 ARQ 重传。</div>')
    with st.container(border=True):
        heading('点对点通信实验','A → B / ORIGINAL CABLE')
        a,b=st.columns([2,1])
        data=a.text_area('待传输文本','救援现场状态正常，正在通过有噪声的链路发送分片消息。'*12,height=100,max_chars=24000)
        mode=b.selectbox('点对点保护',['Balanced','Fast','Survival'])
        payload=b.select_slider('每片载荷字节',options=[64,128,256],value=128)
        st.caption(f'新任务参数：{modulation} · 噪声标准差 {noise:.2f} · 种子 {int(seed)}')
        a,b,c=st.columns(3)
        if a.button('开始点对点传输',type='primary',use_container_width=True):
            if 'p2p' in st.session_state:
                st.session_state.p2p.close()
            cfg=make_config()
            cfg.payload=payload
            st.session_state.p2p=PointToPointSession(data.encode(),cfg,mode)
            st.session_state.p2p_playing=True
        if b.button('点对点暂停 / 继续',use_container_width=True):
            st.session_state.p2p_playing=not st.session_state.get('p2p_playing',False)
        if c.button('单步发送一个分片',use_container_width=True):
            st.session_state.p2p_playing=False
            if 'p2p' in st.session_state:
                st.session_state.p2p.step()
    point_monitor()


def experiment_view():
    st.session_state.playing=False
    heading('实验结果与对照','RECORDED MEASUREMENTS')
    path=ROOT/'outputs/experiments/results.json'
    if not path.exists():
        st.info('尚无实验结果。请先运行 python experiments/run_all.py --quick。')
        return
    results=json.loads(path.read_text(encoding='utf-8'))
    html(f'<div class="record-hint">以下为已保存的离线实验，并非当前场景的实时统计。生成于 '
         f'{escape(results["generated_utc"])} · {"quick 小样本" if results["quick"] else "full"}。结论以实际数据为准。</div>')
    options={'SOS 优先调度':'scheduling.png','自适应保护':'adaptive.png','多种调制':'e3_modulations.png',
             '信道编码':'e4_coding.png','编码与有效速率':'e4_goodput.png','香农参考':'e2_shannon.png','停等与 GBN':'transport.png'}
    selected=st.selectbox('对照实验',list(options))
    chart=path.parent/options[selected]
    if chart.exists():
        with st.container(border=True):
            st.image(str(chart),use_container_width=True)
    notes={'SOS 优先调度':'优先调度降低 SOS 排队，代价是普通图片可能更晚完成；不抢占已开始发送的帧。',
           '自适应保护':'Auto 根据反馈切换保护，但不保证在每种场景下都优于固定策略。',
           '香农参考':'原版 Cable 没有带宽参数。这里是明确假设下的参考，不等于已验证理想带限信道容量。',
           '停等与 GBN':'统一模拟时钟比较网络效率；Python 计算运行耗时不是网络时延。'}
    st.caption(notes.get(selected,'结合原始配置、样本量、能量与带宽条件解读，不只比较单个成功率。'))
    st.download_button('下载离线实验 JSON',path.read_bytes(),'experiment_results.json',mime='application/json')
    with st.expander('五分钟录制 / 现场展示顺序'):
        st.markdown('1. **Level 1**：点对点页展示非零噪声、分片和恢复文本。\n'
                    '2. **Level 2**：载入星形转发场景，展开链路详情，展示两跳 Cable 和目的地址。\n'
                    '3. **Level 3 现场**：完整 Demo 推进至预览后暂停，再观察 SOS、保护切换和原图校验。\n'
                    '4. **实验**：展示真实离线对照，并说明性能收益与代价。')


if page=='Level 1 · 点对点':
    level1_view()
elif page=='实验与对照':
    experiment_view()
else:
    if page=='Level 2 · 星形转发':
        html('<div class="record-hint">LEVEL 2 / 源地址 → Switch 查表 → 目的端口。展开下方链路详情，查看真实帧头与各方向 Cable 调用。</div>')
        if st.button('载入 Level 2 场景'):
            new_network()
            n=st.session_state.net
            n.send(1,4,Message('TEXT','level2-a-d',{},'A→D：现场状态正常。'.encode()))
            n.send(3,2,Message('STATUS_QUERY','level2-c-b',{}))
            st.session_state.notice='A→D 文本和 C→B 状态查询已提交 · 点击继续或单步'
    controls()
    network_monitor()
    task_controls()
    composer()
