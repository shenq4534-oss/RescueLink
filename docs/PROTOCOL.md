# RescueLink v1 协议

全部整数为网络字节序，大端。链接只接受完整定界的采样数组；已知帧起始和采样相位，不做任意流中的搜索同步。存在前导并验证相似度，PHY 头确定后续精确长度。

## 物理帧

48 ksample/s（下行按配置倍率降低），BPSK/OOK 第一载波 6kHz，BFSK 第二载波 12kHz；每符号 8/16/64 样本是完整整数周期，低于 Nyquist。Fast = BPSK / 8 / 无 FEC，Balanced = BPSK / 16 / SECDED，Survival = BPSK / 64 / SECDED。UI 允许固定实验调制覆盖载波方案；模式仍控制符号时长与 FEC。

固定前导 `10110010` 重复 4 次，32 bits。固定 PHY 头 `!BBBBH`：版本1 byte（1）、调制 ID1 byte（BPSK=1/ASK=2/BFSK=3）、FEC1 byte（0/1）、每位样本数除以8的1 byte（1/2/8）、原始链路帧字节数2 bytes（1–1024）；然后头部 CRC32 4 bytes。头部每 bit 重复三次，固定 BPSK 64 样本/bit，多数表决。头和前导共 17408 samples。译头后要求采样数组长度恰好等于固定头＋`length*8*(fec?2:1)*spb`，否则拒绝。

前导的最小二乘增益估计用于 OOK 门限；训练残差估计 SNR。前导 >3 bit 错、头 CRC 错、非法模式、采样长度不符均丢弃。没有从发送方传入 payload 长度或当帧模式用于解码。

Hamming(8,4)：位置1/2/4为校验位，3/5/6/7为数据，8为总偶校验。综合 syndrome 和总奇偶：单错翻转定位位、整体校验位单错翻转8、非零 syndrome 且偶校验为双错拒收。三位及以上可能误纠，因此纠错后继续 CRC。CRC 之后编码，每字节恰好两个码字，无额外 padding。

## 链路 Header：21 bytes + payload + CRC32(4)

对应 `struct.Struct('!BBBBBIIHHHH')`。

|偏移|字段|长度|有效范围|
|---|---|---|---|
|0|version|1|1|
|1|frame_type|1|DATA=1 ACK=2 NACK=3 WINDOW_UPDATE=4 PROBE=5 LINK_REPORT=6|
|2|src|1|1–254，网络应用 Host 1–4，报告使用254|
|3|dst|1|1–254，未配置地址由 Switch 拒绝|
|4|priority|1|SOS/控制报告=0，元信息/预览=1，普通/原图=2|
|5|message_id|4|1–2³²−1，一个引擎内全局不复用|
|9|sequence|4|DATA=fragment_index，ACK=下一个期望序号；无回绕|
|13|fragment_index|2|0≤index<count；控制帧为0|
|15|fragment_count|2|1–65535|
|17|advertised_window|2|0–64，剩余接收缓存槽数|
|19|payload_length|2|0–256|

CRC32 保护完整 Header 与 payload。先校验 CRC，再解字段；截断、附加字节、未知类型/版本、非法地址/窗口/长度、DATA 序号不匹配均拒收。ACK/NACK/WINDOW_UPDATE/PROBE 无 payload。LINK_REPORT payload 恰好3 bytes：方向0(up)/1(down)，端口1–4，质量0坏/1可接受/2高SNR干净。质量0：解码失败或训练 SNR<1；质量2：SNR>4 且无纠正；其它为1。报告优先级0、Survival 保护；报告不再生成报告，避免递归反馈。

## 可靠传输与流控

会话 key `(dst,src,message_id)`；每条应用消息独立序号0..count−1，不跨消息回绕。Stop-and-Wait 窗口1；GBN 窗口配置1–64。pending 范围 `[base,next_seq)`，最大允许 `min(sender_window,advertised_window)`。

接收 DATA 仅在 `seq==expected` 且目的 Host 全局缓存未满时入有限槽；expected 前移，返回累计 ACK（next expected）和剩余槽。应用按 process_delay 异步消费槽，完整字节重组才解析 UTF-8/应用。`seq<expected` 返回当前累计ACK，不重复交付；`seq>expected` 丢弃乱序并 NACK expected。重组类本身支持乱序/去重，可靠协议选用严格 GBN 乱序丢弃。

ACK 前移 base 并滑动发送窗口。NACK 对同一个 base 仅触发一轮快速 GBN 重传；重复 NACK 不产生风暴。最老未确认窗口超时重发 `[base,next_seq)`，记真实计数。ACK 进展清零连续超时轮数；超过 max_retries 标记 failed；应用可能已经收到而确认耗尽，统计区分 delivered/acked/failed。

Host 缓存曾满、消费后释放槽时，对该 Host 的所有会话发送 WINDOW_UPDATE。通知丢失时，发送方零窗口超时发 PROBE，接收端返回窗口更新。控制帧也可能丢失，计时器与重试上限保证最终退出。缓存按 Host 而不是无限每流资源计数。

保守 RTO 为 `max(config.rto,(window+max_queue+2)*max_frame_duration*(2+2*downlink_multiplier)+4*propagation)`。估计用最长模式，避免短暂排队触发重传；可能过于保守并降低坏链路完成速度。LINK_REPORT 失败依赖业务 ACK 超时，无无限探测。

## 应用协议

4 bytes JSON metadata 长度（1–8192）＋UTF-8 JSON＋opaque body；总长≤2 MiB。JSON 精确包含 `type`、`request_id`（1–64字符）、`meta` 对象。未知 type、非法 schema/长度拒收。请求响应独立 message_id，同一 request_id 关联。

```json
{"type":"SOS_ALERT","request_id":"sos-1","meta":{"sector":4}}
```

body 可为 `SOS：四区需要救援`。目标生成 SOS_ACK，沿真实双跳返源；STATUS_QUERY 对应带 host/state 的 STATUS_RESPONSE。

图片过程：IMAGE_META（sha256、size、format、width、height、preview_size）→READY(next=preview)→IMAGE_PREVIEW→READY(next=original)→IMAGE_ORIGINAL→校验后 IMAGE_RECEIVED。仅原图模式在第一个 READY 后跳过预览。ERROR 返回失败原因。接收端图片状态按 `(src,request_id)` 隔离；仅从真实收到的 body 显示图片、计算 hash。request_id 限安全字符；自行生成落盘文件名并验证输出目录，禁止使用远端路径。

图片状态：等待→元信息到达→预览可用→原图分片中→完整验证成功/失败。少片不解码原图。原图校验还检查格式、尺寸、长度。所有实际内容仅在完整字节重组、CRC 成功后交付。

## 观测追踪（不属于线上协议）

`PhysicalLink(capture=True)` 在实际 Cable 调用边界采集发送链路帧、编码位串、返回波形和解调/译码结果。该开关仅影响诊断数据；`decode()` 仍只使用收到的采样数组。捕获的源端字节、源端模式和哈希不作为接收端解码参数。

快照包括 cable.py 文件 SHA-256、每方向调用序号、完整波形的 float64 little-endian SHA-256、原版 Cable 保存的输入/输出与适配器的数组一致性、PHY 头独立解码结果、完整发送/接收编码位、译码候选、有效正文。只有 FEC/CRC 均通过才填入 `payload_hex_rx` 和有效接收帧哈希；失败候选只能诊断，不进入应用层。

帧哈希关联一次上行接收与下一跳发送；样本哈希关联物理输入/输出，两者含义不同。波形图最多放大正文附近24个编码位（短正文之后可能包含CRC），完整样本用哈希关联。网络界面保留最近80个详细快照以限制内存，全部紧凑发送记录仍可下载；点对点教学实验保留当次所有分片。

这些记录来自程序自身，不能代替独立审计或提供防篡改保证。`tests/test_trace.py` 通过捕获原版实际调用、替换返回信号和阻断特定下行验证系统对物理路径的因果依赖；故障注入与正式噪声模型严格分开。
