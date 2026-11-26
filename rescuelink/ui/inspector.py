"""Read-only views of samples and bytes observed inside the real PHY pipeline."""
import json
import streamlit as st
import plotly.graph_objects as go
from rescuelink.config import MODES
from rescuelink.protocol.frame import Frame, HEADER
from rescuelink.simulation.scenarios import level1


def show_frame(trace, key):
    sent = Frame.unpack(bytes.fromhex(trace["frame_hex_tx"]))
    st.caption(f"{trace['lane']} · Cable 调用 #{trace['cable_call']} · "
               f"message={sent.message_id}, sequence={sent.sequence}, {sent.kind.name} · "
               f"{trace['mode']} / {trace['modulation']}")
    step = st.radio("查看步骤", ["1 字节→比特", "2 成帧→编码", "3 调制→Cable", "4 解调→校验"],
                    horizontal=True, key=f"{key}-step")
    if step.startswith("1"):
        st.write("发送端片段正文：十六进制与逐字节的 MSB-first 比特。中文按 UTF-8 编码，收齐后才解码。")
        st.dataframe([dict(offset=i, hex=f"{b:02x}", decimal=b, bits=f"{b:08b}")
                      for i,b in enumerate(sent.payload[:32])], hide_index=True)
        st.code(" ".join(f"{b:08b}" for b in sent.payload), language="text")
    elif step.startswith("2"):
        st.write("链路帧 = 21 字节 Header + 正文 + 4 字节 CRC；随后按模式进行 Hamming 编码。")
        st.json(dict(src=sent.src, dst=sent.dst, priority=sent.priority, message_id=sent.message_id,
                     sequence=sent.sequence, fragment_index=sent.index, fragment_count=sent.count,
                     advertised_window=sent.window, payload_bytes=len(sent.payload)))
        raw = bytes.fromhex(trace["frame_hex_tx"])
        st.code(f"Header: {raw[:HEADER.size].hex(' ')}\n"
                f"Body:   {sent.payload.hex(' ')}\nCRC32:  {raw[-4:].hex(' ')}", language="text")
        st.write(f"信息位 {len(trace['frame_bits_tx'])} → 编码位 {len(trace['coded_bits_tx'])}。")
        st.caption("以下显示完整链路帧开头的 128 位；完整序列可在下载的 JSON 中复查。")
        st.code("编码前: " + trace["frame_bits_tx"][:128] + "\n编码后: " + trace["coded_bits_tx"][:128], language="text")
    elif step.startswith("3"):
        st.write("实际调用：编码位 → 调制采样 → cable.Cable.transmit → 返回采样。")
        st.caption(f"完整波形共 {trace['samples']} 个样本；固定 PHY 前缀占 "
                   f"{trace['payload_offset_samples']} 个样本，波形图放大正文起点（控制帧从 CRC 起），最多 24 个编码位。")
        # Body samples include any following CRC if the body is shorter than the view.
        fig = go.Figure()
        start = trace["body_offset_samples"]
        fig.add_scatter(x=list(range(start,start+len(trace["body_tx"]))), y=trace["body_tx"], name="实际 TX")
        fig.add_scatter(x=list(range(start,start+len(trace["body_rx"]))), y=trace["body_rx"], name="Cable 返回 RX", opacity=.7)
        fig.update_layout(height=300, xaxis_title="完整物理帧中的样本下标", yaxis_title="幅度", margin=dict(t=20,b=40))
        st.plotly_chart(fig, use_container_width=True, key=f"{key}-wave")
        st.json(dict(teacher_class=trace["cable_class"], cable_call=trace["cable_call"],
                     teacher_saved_input_matches=trace["cable_input_matches"],
                     teacher_saved_output_matches=trace["cable_output_matches"],
                     teacher_source_sha256=trace["cable_source_sha256"],
                     tx_waveform_sha256=trace["waveform_sha256_tx"],
                     rx_waveform_sha256=trace["waveform_sha256_rx"]))
    else:
        st.write("接收端独立读取固定 PHY 头，再解调、纠错，最后验证链路 CRC。")
        header = trace.get("phy_header_rx")
        if header:
            st.json(header)
        if trace["coded_bits_rx"] is not None:
            offset = trace["body_coded_bit_offset"]
            tx,rx = trace["coded_bits_tx"], trace["coded_bits_rx"]
            st.dataframe([dict(coded_bit=i, tx=tx[i], rx=rx[i], error=tx[i]!=rx[i])
                          for i in range(offset,min(offset+64,len(tx)))], hide_index=True)
            st.write(f"纠正码字：{trace['corrected_codewords']}；不可纠正：{trace['detected_uncorrectable']}。")
        if trace["ok"]:
            st.success("链路 CRC 通过：以下是接收字节，不是发送端原文的副本。")
            st.code(bytes.fromhex(trace["payload_hex_rx"]).hex(" "), language="text")
            st.write("发送帧与有效接收帧 SHA-256 一致：", trace["frame_sha256_tx"] == trace["frame_sha256_rx"])
        else:
            st.error("拒收：" + trace["error"])
            st.caption("未通过 FEC/CRC 的候选字节只保存在诊断 JSON，不能作为收到的业务内容。")
    st.download_button("下载此帧完整追踪 JSON", json.dumps(trace,ensure_ascii=False,indent=2),
                       f"{trace['lane']}_{trace['cable_call']}.json", key=f"{key}-download")


def point_to_point_lab(noise, scheme, seed):
    st.subheader("Level 1 · 底层实验室")
    st.write("一个发送端直接通过老师 Cable 连接一个接收端。按步骤展开同一帧的真实中间结果。")
    text = st.text_area("教学文本", "SOS：请救援", max_chars=512)
    cols = st.columns(2)
    mode = cols[0].selectbox("实验保护模式", list(MODES), index=1)
    size = cols[1].selectbox("每片正文上限（字节）", [16,32,64,128], index=1)
    st.caption(f"本次按钮运行将使用左侧噪声={noise:.2f}、调制={scheme}、种子={seed}。无自动重传，用于直接观察成功与失败。")
    if st.button("运行逐层实验", type="primary"):
        st.session_state.pop("lab_result",None)
        with st.spinner("实际生成波形并调用原版 Cable…"):
            st.session_state.lab_result = level1(text.encode(),noise,size,scheme,mode,True,int(seed))
    result = st.session_state.get("lab_result")
    if not result:
        return
    st.caption(f"已保存实验快照：{result['mode']} / {result['scheme']} / noise={result['noise']} / seed={result['seed']}；修改控件后需重新运行。")
    cols = st.columns(3)
    cols[0].metric("分片数",result["fragments"])
    cols[1].metric("真实 Cable 调用数",result["cable_calls"])
    cols[2].metric("成功帧数",sum(r["ok"] for r in result["records"]))
    st.write("发送端字节：")
    st.code(bytes.fromhex(result["sent_hex"]).hex(" "),language="text")
    if result["received_hex"] is not None:
        actual = bytes.fromhex(result["received_hex"])
        st.write("接收端完整重组文本：")
        st.code(actual.decode("utf-8",errors="replace"),language="text")
        if result["success"]:
            st.success("完整字节一致")
        else:
            st.error("已重组，但字节不一致")
    else:
        st.warning("至少一个分片缺失或校验失败：接收端没有完整消息。")
    index = st.selectbox("查看分片", list(range(result["fragments"])),
                        format_func=lambda i:f"分片 {i+1}/{result['fragments']}", key="lab-fragment")
    show_frame(result["records"][index]["trace"],"lab-frame")
    st.download_button("下载本次全部分片追踪",json.dumps(result,ensure_ascii=False,indent=2),"level1_trace.json")
    st.info("这是可复查的程序观测记录。哈希用于关联阶段，不是独立防篡改认证；验证是否依赖 Cable 还应结合源码和阻断测试。")


def network_inspector(network):
    st.write("按 message_id + sequence 对照同一片段经过的上行、下行与返回确认。每行均来自真实物理发送。")
    groups = sorted({(a["message_id"],a["sequence"]) for a in network.attempts if a["frame_type"]=="DATA"})
    if not groups:
        st.info("先发送一段文字，再查看这里。暂停后更方便逐帧检查。")
        return
    mid,seq = st.selectbox("消息 / 片段序号",groups,format_func=lambda x:f"message={x[0]} / sequence={x[1]}")
    related = [a for a in network.attempts if a["message_id"]==mid and
               (a["frame_type"]!="DATA" or a["sequence"]==seq) and a["frame_type"]!="LINK_REPORT"]
    st.dataframe([dict(start=a["start"],lane=a["lane"],type=a["frame_type"],sequence=a["sequence"],
                       mode=a["mode"],valid=a["ok"],tx_frame_sha256=a.get("frame_sha256_tx"),
                       valid_rx_frame_sha256=a.get("frame_sha256_rx")) for a in related],hide_index=True)
    traces = [t for t in network.traces if t["message_id"]==mid and t["sequence"]==seq and t["frame_type"]=="DATA"]
    st.caption("表中哈希关联完整链路帧字节；上行接收哈希与下行发送哈希可对照。控制 ACK 的 sequence 是累计确认号。详细波形只保留最近 80 次发送，完整紧凑事件日志不受此限制。")
    if traces:
        i = st.selectbox("展开一次 Cable 调用",list(range(len(traces))),
                         format_func=lambda i:f"{traces[i]['lane']} #{traces[i]['cable_call']} @ {traces[i]['start']:.4f}s")
        show_frame(traces[i],"network-frame")
    else:
        st.info("该帧详细快照已过期；可重置后只发一条短消息，立即暂停检查。")
