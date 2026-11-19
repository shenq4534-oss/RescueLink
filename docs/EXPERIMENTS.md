# 实验方法与指标

执行 `python experiments/run_all.py --quick` 或 `--full`。集中入口内按任务组织函数，避免七份重复脚手架。JSON 保留配置、时间、随机种子、物理帧测量和模式历史；CSV 保存标量；PNG 为实测图。自动验收的具体数值见 [VALIDATION.md](VALIDATION.md)。

|实验|输入与对照|主要输出|
|---|---|---|
|E1|空字节、英文、中文、全字节值、长消息；noise=0/.25|level1 results、真实分片恢复|
|E2|noise=0/.3/.7/1.0/1.4；线性 SNR 的训练估计；另跑星型应用吞吐|e2_shannon.png、noise_network JSON|
|E3|相同符号16 samples；BPSK/ASK/BFSK；相同平均信号功率|e3_modulations.png、Raw BER|
|E4|BPSK、16 samples 同速；无 FEC vs 手写 Hamming|e4_coding.png、e4_goodput.png、纠正/不可纠正数|
|E5|固定 Fast/固定 Survival/Auto；同一消息到达和低→高→低噪声序列|adaptive.png、交付率/时长/吞吐/重传、逐阶段指标、模式驻留/切换|
|E6|FIFO/Priority；B→D 图片、A→D 背景数据、C→D 三条 SOS|scheduling.png、均值/P95、图片完成时间、真实队列峰值|
|E7|Stop-and-Wait/GBN；相同长链路与应用字节数|transport.png、吞吐与重传|
|预览对照|仅原图/预览优先；相同输入图片|首次可用时间、完整恢复时间、额外字节数|

Quick 物理测量每个设置4帧，Full 40帧。Quick 自适应 seeds=42,43，Full 42–47；SOS Quick seeds=42,43,44，Full 42–51。Quick SOS 每种策略有9次应用送达样本，同时保留各 seed 内均值/P95。低噪声下不同 seed 可能给出完全相同的判决结果；真实模拟采样不同不意味着必然产生不同 CRC/时延。小样本不能当作置信区间或一般性优越结论。

## 公平性和边界

E3 BPSK/BFSK 振幅1，OOK振幅√2；平衡随机输入下平均功率约1/2，相同符号采样数、采样率与噪声标准差。BFSK 占用频谱更宽；OOK 噪声判决还受训练增益估计影响。固定头开销在帧吞吐比较中保留，Raw BER 只比较相同位置 payload 编码位，不能声称某种调制在所有能量/频宽约束下绝对最好。

E4 固定每位符号时长，编码帧有两倍 payload 位，因此 airtime 增大；不把 Balanced 比 Fast 降速的收益混称为编码收益。Hamming 会检测而不能恢复所有双错，随机高噪声仍可失败。残余 BER 由已知发送真值与译码结果比较，无法纠正帧仍纳入译码后比特统计（若 PHY 头有效）。

E5 到达时间0,3,…,69s，noise 0.12→12s时1.0→42s时0.12，策略不同导致不同信道占用和抽样次序。相同 seed 和相同外生时间序列是可复现的，并不保证各模式的每个 payload 比特经历完全相同噪声样本。报告可以延迟或损坏，Auto 可能不如最保守策略；切换来自真实反馈，不预设输出。phases 给出三个时间区间的交付位数、吞吐与真实重传数。

E6 下行 DAC/ADC 时钟比上行慢3倍，窗口12，A背景消息模拟8s生成，SOS在12/18/24s到达。两策略只改变调度算法，输入和噪声一致。检查 down4 queue_peak>1，才说明存在竞争；普通流完成和图片 full time 用于说明公平性代价。高优先级包含链路报告与控制，会增加开销。不存在对正在发送帧的抢占。

E7 Cable 长度100km，attenuation=0，noise=.12；把长传播与损耗解耦，属于明确的实验条件，不更改原版 Cable 模型。完整 GBN 采用乱序丢弃，不是 Selective Repeat。

## 统一指标

- Raw BER：PHY 头可解时，发出编码位与解调位的差异/编码位数；包含链路帧 Header/CRC 的编码部分，不含固定 PHY 前缀。PHY 头失败单独计数，不能把无法对齐的整帧当零误码。
- Post-FEC BER：译码后的位与编码前链路帧位差异/这些信息位数；未经过 FEC 的行与 Raw BER 相同。
- FER：全部物理帧尝试中的失败帧比例，包括 PHY、FEC、CRC；重传也是尝试。
- App goodput：所有去重、成功交付应用 body 的位数/引擎总模拟用时；metadata、Header、CRC、控制帧不计有效载荷。所有控制/转发的 airtime 和 ACK 返回都进入时钟。双向应用 body 会分别计数，未确认但实际交付的 body 仍是已交付。
- Single-link goodput：物理实验中 CRC 成功的128-byte测试 payload 位数/该链路总 airtime+传播；区别于星型端到端 goodput。valid_frame_bps 额外保留，包含链路头，不用它冒充应用吞吐。
- SOS latency：完整 SOS_ALERT 应用接收时间减生成时间；不是队列等待时间，也不要求等 SOS_ACK。
- Retransmissions：源端重新入队 DATA 的数量，不把 ACK、原始 Switch 转发计入。
- Duration：最后实际链路到达/应用处理或真实失败时刻；过期计时器跳过；单一仿真秒基准，非 CPU 秒。
- Mode airtime：该模式全部真实物理帧的占用和；Mode residence：每条链路控制器处在该模式的模拟时间。并行端口 airtime 之和可大于总时长。

## Shannon 参考

固定训练 `x`、实际接收 `y`：`gain=(y·x)/(x·x)`，`noise_power=mean((y-gain*x)^2)`，`signal_power=mean((gain*x)^2)`，`SNR_linear=signal_power/noise_power`。图用 `B=24000 Hz`（采样 Nyquist 范围的等效低通假设）计算 `C=B*log2(1+SNR_linear)`。

老师 Cable 是离散加性白噪声和幅度衰减，并未物理限带，系统载波也不是理想砖墙频谱。因此这只是说明容量随实测 SNR 变化的参考，不能当作严格容量上界验证。零噪声理想容量趋于无穷；数值计算用1e−15噪声功率下限，图上有限大值是数值下限导致。没有把 noise_level 或 dB 数直接代入公式。

所有报告及图使用真实通信引擎测量；单元测试的受控丢包/翻位只验证异常路径，不参与实验图。
