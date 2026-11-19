# RescueLink — 交给 Codex 的完整开发任务（请直接执行，不只输出规划）

你是一名具有 Python、数字通信、计算机网络、离散事件仿真、多线程和测试经验的高级软件工程师。你现在要在**当前工作区**从头到尾实现一个可运行、可展示、可测试、可复现的课程项目。项目名称：

**RescueLink — Adaptive & Reliable Emergency Communication Network（自适应可靠应急通信网络）**。

**行动要求：**不要只给设计文档、伪代码、目录结构或最小样例。要实际创建/修改所有需要的源代码、测试、示例资源、运行脚本和文档，并运行测试，修复错误直至通过。不要在做完 Level 1 后停下。不要在开发到一半时反问我技术选项；下面是完整需求，细节可由你作合理工程决策并写入文档。若执行环境限制使某项无法验证，要如实说明，绝不能把未实现/未测试的功能写成完成。

## 0. 首先检查当前工作区

1. 列出已有文件，阅读最新的 `README(1).md`（或课程 README）、`cable.py`、`requirements.txt` 以及任何现有代码。如果这些课程文件不在当前工作区，先在合理位置查找；若仍找不到，在 README 中明确列出缺失项并仅为**本地开发**提供兼容性适配/测试替身，不能把替身当成正式提交的老师原版 `Cable`。优先要求使用者把原版 `cable.py` 放到项目根目录。正式通信路径必须能直接使用老师提供的 `Cable`。
2. 以课程要求为最高优先级。不要改动老师提供的 `cable.py` 的物理模型来“修复”误码，不要用伪造数据绕过它。可以在外围封装线程安全、独立上下行方向、随机种子、日志统计。
3. 用尽量少且可靠的依赖完成项目。建议 Python 3.11+、NumPy、Matplotlib、Pillow、Streamlit、Plotly、pytest；其他依赖只有真正必要才增加。不能依赖云服务、在线 API、网络数据库或大模型推理。
4. 先完成可运行的核心通信链路，再接入 UI。核心库必须能在不启动 Streamlit 的情况下工作，命令行和 pytest 均可验证。
5. 在内部维护开发任务清单，但始终继续编写代码、运行验收，不要只输出一个开发计划。

## 1. 项目目标与课程评分对应

必须完整实现：

- **Level 1（30 分）点对点通信：**任意数据/UTF-8 文本→比特→实际调制波形→原版 `Cable.transmit()`→解调→比特→原始数据；短消息、长消息真实分片/重组、CRC 检错；带噪声传输；不同噪声条件的吞吐率、SNR 和香农容量参考分析。
- **Level 2（30 分）多主机：**至少 4 台 Host ＋ 1 台中央 Switch，**星型拓扑**，不允许全连接；每台 Host 以 Cable 上下行连接中央节点；唯一主机地址、带 Header 的数据帧、中央节点按目标地址转发；处理不同主机的并发请求，不能因为处理一条消息就静默丢弃其他端口的消息。
- **Level 3（最多 40 分）扩展：**完整落地可靠传输（ACK/NACK、序号、超时重传、流控）、信道编码（Hamming/CRC、纠错测试）、应用层协议（请求—响应、协议解析），并尽可能实现 ASK/BFSK/BPSK 对比及多线程并发。**无线/MIMO不是本次必做，不得为了增加名目牺牲系统质量。**

此外，本项目真正的差异化体现在下述 **三个创新功能，全部为必做、必须有真实逻辑和现场可演示路径**：

1. **Adaptive Transmission：自适应通信保护**：根据真实接收反馈或导频/训练序列估计的链路质量，在 Fast / Balanced / Survival 模式间切换，且能与固定模式做可复现实验对比。
2. **Priority-Aware Networking：SOS 紧急消息优先**：当普通图片/文件传输占用输出链路时，新来的 SOS 在下一帧可调度时机得到优先服务；不能中断已经发送的一帧；要避免普通业务永久饿死；可对比 FIFO 与优先级队列的 SOS 延迟。
3. **Progressive Image Transmission：图片优先预览**：先发 SOS/文字元信息，再发同一图片的低分辨率缩略图，最后发原图；接收端实际经过协议收到缩略图后立即展示，最终从收到的完整字节重建图片并校验 SHA-256。不是把发送端的本地图片路径直接交给接收端渲染。

项目情境：现场终端 A（状态/传感器）、B（现场图片）、C（SOS/救援）、D（指挥中心）。所有终端都能收发数据，默认 C 向 D 发送 SOS，B 向 D 上传图片。界面能够模拟 B 的图片上传过程中 C 突发 SOS；链路噪声上升后自适应保护启动，最终图片恢复完整。

## 2. 严格的真实性约束（非常重要）

- 每一次业务 DATA 帧、ACK/NACK、窗口/控制帧、应用层 RESPONSE，以及每一次 Switch→Host 转发，**都必须经过真实的调制→`Cable.transmit`→解调流程**。绝不能在 Host 间用函数直接传输明文、位串、文件字节或 ACK 作为最终送达方式。
- `Cable` 可以被封装，但不能用随机按概率直接翻位替代物理信道。人为翻位只能用于单元测试纠错能力，与实际 Cable 噪声实验严格区分。
- 不允许通过传输开始前知道完整内容而让接收端“恢复”数据；只有验证成功的真实接收字节才能进入接收端应用层。
- 不允许造假事件日志、重传次数、性能图或完成时间。日志和图表必须来源于通信引擎的事件/统计。
- 初版可以假定理想同步（发送与接收共享采样率、符号时长、载波参考），但必须有明确帧前导和确定的物理帧长度机制，写清理想同步的边界。
- 如果使用模拟时钟进行传播延迟、链路占用和重传计时，所有性能指标都必须采用**相同的仿真时间基准**，不能把 Python 的 CPU 执行时间当成网络传输时间。`get_propagation_delay()` 应被纳入模型。
- 对“成功率100%”等结果要忠实计算；达到重传上限、无法解码、无合法地址、损坏帧等都必须真实报告失败。
- 任何预设 Demo 场景都只能预置输入、随机种子与信道变化，不能预置假输出或事先伪造成功的接收消息。

## 3. 推荐架构（可合理微调，但功能必须都有）

建议如下目录，按责任组织，必要时自行增加模块：

```text
RescueLink/
├── README.md
├── requirements.txt
├── pyproject.toml                 # 如果合适，配置 pytest/包结构
├── cable.py                       # 原版，存在时保留不改
├── main.py                        # CLI 入口
├── app.py                         # Streamlit 入口
├── rescuelink/
│   ├── __init__.py
│   ├── config.py                   # 全部参数、模式定义、随机种子
│   ├── events.py                   # 类型化事件、日志、统计
│   ├── physical/
│   │   ├── bits.py                # UTF8/字节/比特转换
│   │   ├── modulation.py          # BPSK、ASK、BFSK 调制解调
│   │   ├── coding.py              # Hamming(8,4) SECDED
│   │   ├── framing_phy.py         # 前导/固定物理头/载荷的编解码
│   │   └── channel.py             # 老师 Cable 的适配封装
│   ├── protocol/
│   │   ├── frame.py               # 严格二进制 Header/CRC
│   │   ├── fragmentation.py       # 分片/重组/去重
│   │   ├── transport.py           # Stop-and-Wait / GBN / 超时/窗口
│   │   └── application.py         # 应用消息的类型与解析
│   ├── network/
│   │   ├── host.py                # 四类终端、消息接口
│   │   ├── switch.py              # 星型转发、端口队列
│   │   ├── scheduler.py           # FIFO / 公平优先级队列
│   │   ├── concurrent.py          # 独立端口线程、同步、安全关闭
│   │   └── adaptive.py            # 反馈驱动的模式切换
│   ├── media/
│   │   └── image_transfer.py      # 缩略图、原图、校验与落盘
│   ├── simulation/
│   │   ├── clock.py               # 虚拟时间或一致的传输时间管理
│   │   ├── scenarios.py           # 一键运行实验/场景
│   │   └── metrics.py             # BER、FER、Goodput、SOS延迟
│   └── ui/
│       └── panels.py              # 可复用的 Streamlit 界面板块
├── experiments/
│   ├── run_all.py
│   ├── shannon.py
│   ├── modulations.py
│   ├── coding_comparison.py
│   ├── adaptive_comparison.py
│   ├── scheduling_comparison.py
│   └── transport_comparison.py
├── tests/
│   ├── test_level1.py
│   ├── test_level2.py
│   ├── test_transport.py
│   ├── test_coding.py
│   ├── test_adaptive.py
│   ├── test_priority.py
│   ├── test_image.py
│   └── test_concurrency.py
├── assets/                         # 小型、可复现的示例图片（自行生成）
├── outputs/                        # 输出图表/日志/接收文件
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROTOCOL.md
│   ├── EXPERIMENTS.md
│   ├── PRESENTATION_5MIN.md
│   └── REQUIREMENTS_TRACEABILITY.md
└── scripts/
    ├── run_level1.py
    ├── run_level2.py
    └── run_showcase.py
```

若工作区已有项目结构，尽量兼容现有文件，而不是无条件覆盖。

### 3.1 数据链路与中央 Switch

- Host 01/02/03/04 与唯一中央 Switch 构成星型，每个 Host 与 Switch 的上下行用独立方向的 `Cable` 对象（或经明确线程安全处理的 Cable 连接）模拟。没有 Host→Host 直连。
- Host 发送：应用消息→分段→可靠传输 Header→链路 Frame/CRC→可选 Hamming→调制→Host 上行 Cable→Switch 接收端解调、译码、验 CRC。
- Switch 从有效 Frame 中读取 `dst_id`，查询目标端口，放入对应出站队列，重新成帧并通过下行 Cable 发出。Switch **不能**将原始数据帧字节直接注入接收 Host；必须重新物理发送。ACK、响应同理。
- 目标地址未知时拒绝并记录明确事件，不广播业务敏感数据。
- 采用每个输入端口可以独立接收、每个输出端口独立排队/发送的结构；不同目的端口可以并发工作，同一物理输出链路不能在同一时刻发送多帧而发生不受控覆盖。
- 记录 source、destination、message ID、fragment/sequence、lane/port、链路、时间、帧字节数、当前编码调制模式、CRC/纠错/重传事件。

### 3.2 严格二进制帧协议

设计、实现并在 `docs/PROTOCOL.md` 精确写明每个字段的长度、字节序、有效范围、解析失败行为。建议包含：`version`、`frame_type(DATA, ACK, NACK, WINDOW_UPDATE)`、`src_id`、`dst_id`、`priority`、`message_id`、`sequence`、`fragment_index`、`fragment_count`、`advertised_window`、`payload_length`、`payload`、`CRC-32`。

- 长消息按最多 128 或 256 字节有效载荷分片（作为可配置参数），重组时允许乱序处理及重复片段过滤，严格验证总片数和长度。UTF-8 解码必须发生在完整字节重组以后。
- CRC-32 保护需要保护的头字段＋载荷；校验失败的帧不进入上层。
- ACK、NACK、控制帧也有完整帧头和 CRC，经 Cable 传输。
- 保护未知类型、格式错误、截断、超限载荷、重复消息、非法地址等边界情况。

### 3.3 物理层与模式切换的兼容性

默认 BPSK：自行实现载波波形、判决；提供 ASK/OOK 和相干 BFSK 作为实验模式。明确采样率、samples per bit、载波频率、符号持续时间，选择避免混叠的参数；实验比较使用有意义的相同能量/带宽或说明限制，不得把不公平参数组合当成某种调制绝对更优的结论。

**关键：每帧必须具有固定且稳健的 PHY 帧头，接收者才能知道后续载荷的编码与调制参数。**推荐：固定 BPSK/固定符号时长的前导＋受保护的物理头，含载荷调制方案 ID、FEC 方案 ID、载荷符号长度、消息版本、物理头 CRC；必要时对物理头做简单双重校验/重复编码。接收端先解固定头，再依据其配置解 payload。物理头不能依赖尚未知晓的 payload 模式。若 PHY 头损坏，则丢弃并依靠可靠传输恢复。

- Fast：BPSK、无 FEC、较快符号率。
- Balanced：BPSK、Hamming(8,4) SECDED、正常符号率。
- Survival：BPSK、Hamming(8,4)、较保守符号率/更长每比特周期。
- 每个模式要记录原始信息比特数、编码后比特数、波形样本数、传输模拟耗时。不能把增加冗余导致的速率损失隐藏。
- 对外展示实际发出与收到的波形采样片段、检测出的错误、译码统计。

### 3.4 Hamming 与 CRC

手写 Hamming(8,4) SECDED 编译码，不用外部纠错库替代；提供 `corrected_codewords`、`detected_uncorrectable` 等统计。每个 8 位码字可纠正单比特错、检测双比特错；不承诺处理任意多个错误。编码位置位于 CRC 之后，接收时先译码再校验 CRC。使用明确的 padding/原始字节长度避免输出多余字节。

### 3.5 可靠传输、流控、超时与端到端语义

至少提供可切换的 Stop-and-Wait 和 Go-Back-N（GBN，默认可选窗口如 4）。正确维护 per-flow sequence、pending frames、ACK/NACK、累计 ACK、超时与重传、重复包丢弃、最大重试、失败通知；端到端 ACK 必须经 Switch 和 Cable 返回源 Host，不能通过线程间直接调用伪造确认。

- 为接收端设计**真实有限容量**的接收缓冲区或应用处理队列，在 ACK/窗口控制帧中携带可用窗口；发送端遵守通告窗口，上限是 `min(sender_window, advertised_window)`。零窗口要有恢复通知/探测，不能死锁。
- GBN 的累计 ACK 和乱序丢弃规则必须写清楚，并确保序号回绕/会话隔离或在当前项目范围内安全限制序号范围。
- Switch 排队不改变业务的传输顺序语义，优先级应按流/片段一致设置；消息由接收端完整重组后才作为应用消息交付。
- 超时阈值要基于帧发送占用时间、两跳传播延迟、排队及 ACK 返回考虑，避免正常排队导致无穷重传。可以有可配置的保守 RTO 和上限，不需要实现完整 TCP。

### 3.6 多线程与模拟时间

课程将 Concurrency 作为可选扩展，明确要求多线程。采用 `threading`、`queue.Queue`/`PriorityQueue`、锁/条件变量、干净的 worker lifecycle，让多个 Host 同时提交消息，Switch 不会因某个端口正在处理一条消息而丢弃其他主机请求。提供批量并发压力测试，覆盖不同目的端口与相同目的端口拥塞。

同时要避免“线程执行得快＝通信快”的错误：设计统一的**模拟链路占用时间与传播时延**：`frame_symbols / symbol_rate + cable.get_propagation_delay()`，适当计入前导、PHY Header、编码额外开销及 ACK；用事件调度或线程安全的仿真时间/每端口下一可用时刻来维护顺序。允许把真实 UI 展示播放速度与模拟时间分开。随机种子固定时，同一组对比实验应能复现；多线程线程调度可能引入非确定性时，要在实验用可复现调度/固定输入到达时间的方法消除对比偏差。不要用大量真实 `sleep()` 拖慢运行。

## 4. 三大创新：逐项详细验收

### 创新 A：Adaptive Transmission（绝对必做）

实现一个真正的 `AdaptiveController`，而不是 UI 按钮改文字。至少支持：

- `Fixed Fast`、`Fixed Balanced`、`Fixed Survival`、`Auto` 四种策略；真实发帧使用所选 PHY 模式。
- 每一发送方向/链路维护最近 N 次帧尝试的反馈（CRC 失败/纠错不可恢复、ACK 超时、成功率），可以加接收端通过固定训练序列得到的 SNR 估计；不得直接读取界面的 `noise_level` 作为控制器所观测的信道质量。
- 用**滞回门限**决定升级/降级：连续一段时间表现差才进入更强保护，连续表现好才切回高效模式，设置最小驻留帧数防止抖动。链路故障无法接收到反馈时，ACK 超时也应视为负面反馈。
- 记录每次 `mode_changed(old,new,reason,time)` 事件、各模式持续时间、切换前后重传与 goodput。
- 注意收发同步：固定保护的 PHY 头携带当帧模式信息；独立解码，不依赖实时控制消息刚好到达。
- 自适应实验：使用固定种子和相同低→高→低噪声序列，对比至少 `Fixed Fast`、`Fixed Survival`、`Auto` 的交付成功率、goodput、重传次数、完成时间和模式变化；不保证 Auto 每个场景都最优，必须如实输出。
- UI 中显示当前实际模式、最近链路质量、切换历史，而不是由按钮直接显示虚构状态。

### 创新 B：Priority-Aware Networking / SOS Priority（绝对必做）

- Switch **按目的输出端口**建立队列，提供 `FIFO` 和 `Priority + anti-starvation` 两种策略。默认正常帧与 SOS 需求共用发送链路的服务机会，排队时间能够通过模拟链路速率体现。
- 至少两档优先级：`EMERGENCY=0` 和 `NORMAL=1`。对于紧急数据，下一次空闲发送机会优先；不抢占已开始发送的单帧。普通业务每处理若干紧急帧后必须有保证服务机会（如权重 3:1 或等待时间 aging），避免 starvation。
- 场景：Host B 在向 Host D 连续上传有很多分片的图片；Host C 在模拟时刻 t_sos 生成 SOS 到 Host D。比较 `FIFO` 和 `Priority` 下 SOS 的**端到端应用送达延迟**（从 SOS 生成时间到 Host D 成功收到完整 SOS 请求）和图片完成时间。
- 在两种策略下使用相同输入负载、链路速度、信道条件、随机种子。必须真实产生竞争（D 的输出端口队列出现 backlog）；若没有拥塞则不应强行制造“优先级明显更好”的假结论。
- UI 提供“开始图片上传 → 触发 SOS”按钮和事件时间线。应显示 SOS 插入队列、下一帧调度、最终收到、可能的普通数据传输延迟。
- 分片级调度使大文件不能以一个超大连续帧堵塞 SOS；但不能虚假宣称正在传输的帧能被中途抢断。

### 创新 C：Progressive Image Transmission（绝对必做）

- 用户可以上传 PNG/JPEG（设置合理大小和图片尺寸上限，避免内存问题），也提供项目内自动生成的原创小型示例图片用于无需外部文件的一键演示。
- 同一张图先发送应用层的 `IMAGE_META`/报警文字，然后发送由 Pillow 生成的低分辨率 `IMAGE_PREVIEW`，最后分片发送真正的原始图片 `IMAGE_ORIGINAL`。三类消息拥有明确 `request_id` / `image_id` 关联。优先级：SOS > 预览图 > 原图的普通数据块，且通过同一个真实网络传输流程。
- 接收端只在从 Cable 真实收到并重组出预览字节后显示预览；原图恢复完成后才显示完整图。对于部分缺失，显示待传进度或占位图，而不是把损坏 PNG/JPEG 强行解码成花屏。
- 计算发送端原图 bytes 的 SHA-256，在接收端对从网络重组收到的 bytes 重新计算 SHA-256 比较；允许接收端安全保存到 `outputs/received/`，限制路径、文件名和文件大小，避免目录穿越。
- 同时显示缩略图首次可用时间 `T_preview`、原图完成时间 `T_full`、数据量、分片数、成功率。可切换“仅原图”与“预览优先”两种策略比较首次可用信息时间和额外开销。
- 应用层必须实现实际有意义的请求—响应：如 `SOS_ALERT`→`SOS_ACK`、`IMAGE_META`→`READY`/`ERROR`、`IMAGE_ORIGINAL`→`IMAGE_RECEIVED`（校验后）、`STATUS_QUERY`→`STATUS_RESPONSE`。所有响应都真实经过网络与 Cable 返回。

## 5. UI（Streamlit）必须是可用的系统，而不是截图

界面建议中文为主、专业清爽，包含：

1. **拓扑与终端面板**：展示 A/B/C/D → Switch 星型结构，各链路有 Cable；当前发送方、接收方及事件高亮。允许选择收发终端。
2. **信道控制**：噪声参数（为每条 Cable 或整个场景设置）；调制模式/自动模式；编码开关；发送窗口；调度策略 FIFO/Priority。输入校验合理，设置在新场景启动时生效。
3. **发送区**：发送 UTF-8 文本；上传小图片；“开始图片上传”；“触发 SOS”；“运行完整 Demo”；“重置”。提供可复用示例，避免课上现场手输大量数据。
4. **接收区**：按来源与目的展示真实收到的消息、预览缩略图、最终图片、SHA-256 校验结果、失败原因、应用响应。显式区分“发送中/预览到达/原图到达/失败”。
5. **技术监控**：统计发送数据帧、ACK/NACK、CRC 错误、Hamming 纠正数、重传数、当前模式、队列长度、仿真时间、goodput、SOS 延迟。实时或分步刷新事件日志。提供一段真实发送与接收波形图以及 E2–E6 的已计算图表。
6. **稳健使用**：Streamlit rerun 不能造成重复启动同一场景，不能泄漏后台线程；有任务运行/停止/复位机制；长实验不要阻塞全部 UI 控件。所有指标必须绑定仿真引擎的状态快照，不能硬编码。

性能图可以使用离线预计算实验结果加载展示；明确标注何时生成、配置与随机种子。默认启动时**无需**重新执行大规模实验，避免展示卡顿。

## 6. 实验、真实指标与香农容量

提供可执行的 `python experiments/run_all.py --quick`（快速）和 `--full`（更完整），将原始结果保存 JSON/CSV、图保存 PNG，且包含配置参数、随机种子、误差解释，不允许写造假的“示例实测值”。至少：

- E1：Level1 空字符串、短英文、中文、随机比特串、长消息分片重组；无噪声与非零噪声；CRC 成败。
- E2：多噪声条件的信道质量、BER/FER、goodput 曲线；计算 Shannon `C=B*log2(1+SNR_linear)` 作为**有声明假设的理论参考**。说明 `Cable` 为离散加噪模型，未自带严格带宽限制；明确怎样从采样率/占用频率作等效带宽假设、如何估计接收 SNR，不能直接将 `noise_level` 或 dB SNR 代入公式，也不能声称模拟吞吐率严格等于 Shannon Capacity。
- E3：ASK / BFSK / BPSK，在可比较的设置下画 BER vs 噪声图；说明公平比较的条件和限制。
- E4：无 FEC 与 Hamming(8,4) 下的 BER、残余误码、纠正数、帧成功率和有效 goodput；编码信息比率带来的开销必须入账。
- E5：固定模式 vs Adaptive，在同一噪声阶段序列下的 goodput、错误率、时延、模式切换事件。
- E6：FIFO vs Priority，同一到达时间与负载下的 SOS 平均/P95 时延、图片完成时间、普通业务公平性；重复多个种子而不是只依赖单次偶然结果。
- E7（推荐）：Stop-and-Wait vs GBN，在相同传播延迟与链路带宽、噪声下比较传输效率及重传开销。

统一指标定义：

- Raw BER：相同位置原始发送比特与解调后比特的错误比例；不要把译码后 BER 混称为 Raw BER。
- Post-FEC BER：译码后的比特错误比例（实验知道真值时可计算）。
- FER：按实际帧计数的错误比例。
- Goodput：成功向应用层交付的**去重有效载荷位数/总模拟用时**（避免把多次重传和重复交付算多次）。
- `SOS_latency = successful_app_receive_time - sos_generation_time`。
- Retransmission count：真实重新发送的数据帧数。
- 计入上行、Switch 排队、下行、ACK 返回；发送比特总数包括物理帧头、编码冗余、控制帧等，按指标分别标注统计口径。

使用合理小样本的 `--quick` 实验满足数十秒或可接受的课程演示准备时间；`--full` 可以更久但需配置。给出脚本命令及图表的明确输出路径。

## 7. 测试与工程质量（不得跳过）

用 pytest 建立独立单元测试与端到端测试，要求至少覆盖：

1. Bit/UTF-8 的双向恢复（含中文、空串、非 ASCII、随机 bytes）。
2. BPSK/ASK/BFSK 在无噪声下波形实际通过老师 Cable 后正确解调；参数限制明确。
3. CRC 对单比特翻转的检测；损坏 Header/载荷拒收。
4. Hamming(8,4) 单比特纠正、双比特检测，原数据字节不发生意外改变。
5. 长消息至少拆成多帧并按序恢复；重复片、乱序或缺片有正确处理。
6. 星型拓扑 4 主机：A→D、C→B 完成转发，未知目标拒绝；检查物理发送计数证明经过 Host→Switch 和 Switch→Host 两次 Cable 调用。
7. ACK 与应用响应也经过 Cable；模拟 ACK 丢失、CRC 失败、超时重传、重试耗尽，保证应用不重复交付。
8. Stop-and-Wait 和 GBN 都能完整送达；接收缓冲区满时遵守 advertised window；零窗口最终可恢复。
9. 自适应控制对坏链路能切换到更保守模式，对持续良好链路能恢复；PHY 头允许每帧独立成功解码其模式。
10. 真正的拥塞场景下，优先级 SOS 调度顺序与 FIFO 不同，且非紧急业务最终能得到服务。
11. 图片 preview 实际先被接收端重组并展示，再完成原图；最终接收字节 SHA-256 完全一致；缺失帧不允许假成功。
12. 多线程同时提交消息，不丢任务、无死锁、可正常退出；固定种子的实验结果可重复。

测试中可注入受控错误或可配置 Cable 替身来检验异常流程，但**正式端到端/界面演示必须调用真实老师 Cable**。测试需要明确区分 `unit/integration/physical_channel`，不因 UI 启动依赖导致整个 pytest 失败。必要时建立小规模/快速测试，避免长时间占用 CI。

必须处理：空数据、非法参数、极大载荷、CRC 错、FEC 不可纠正、未知 Host、重复 DATA、重复 ACK、乱序片段、零窗口、传输失败后的线程清理、UI 重置、中途失败后保持一致状态。

## 8. 文档、演示与最终交付

创建实际可使用的文档：

- `README.md`：产品概览、课程 Level1/2/3 对应表、依赖、安装、完整运行命令、UI 使用方法、一键 Demo、实验命令、测试命令、已知限制。
- `docs/ARCHITECTURE.md`：分层结构、星型拓扑、数据如何在物理链路上传递、线程与模拟时间设计。
- `docs/PROTOCOL.md`：应用层请求/响应例子、完整二进制 Header 字段表、CRC/FEC/PHY 头规则、ACK/NACK/窗口与超时状态机、模式同步设计。
- `docs/EXPERIMENTS.md`：实验方法、公平性、随机种子、评估指标、Shannon 假设和结果图生成方式。只有实际跑出来的数字才写入结果。
- `docs/REQUIREMENTS_TRACEABILITY.md`：课程每条要求→实际实现文件/类/函数→运行命令→测试名/界面位置的映射表，特别列明创新 A/B/C。
- `docs/PRESENTATION_5MIN.md`：**5 分钟、6 页左右 PPT 的中文讲稿与演示脚本**。Level 1、Level 2 需可录屏；Level 3 的自适应、SOS 优先、图片预览有现场按键、日志与实验图支持。包含每段时间预算及当场 Demo 失效时的真实已录屏备选方案（绝不伪造数据）。
- `scripts/run_level1.py`、`scripts/run_level2.py`、`scripts/run_showcase.py` 能分别独立展示 Level 1、Level 2 和完整故事，便于录屏和验收。
- 可选：生成一个测试过的原创小型示例图 `assets/demo_scene.png`，而不是依赖外网照片。

关键时间背景（记录于文档即可）：代码、PPT、其他材料 **12 月 18 日 14:00** 上传 BB；课程报告 **12 月 28 日 23:59**；Presentation **5 分钟**。不必代替我上传或提交，不要声称已经提交。

## 9. 实际实施顺序与完成判定

按以下顺序边编码边测试，**所有阶段都要做完**：

**Phase 1** — 环境检查、Cable API、bits/BPSK、PHY framing、CRC、分片、Level1 CLI；运行对应测试。

**Phase 2** — 四 Host、星型 Switch、双向 Cable、帧头寻址、多端口接收与转发、Level2 CLI；运行对应测试。

**Phase 3** — Hamming SECDED、Stop-and-Wait、GBN、可靠 ACK/NACK、流控、请求—响应协议；全链路端到端验证。

**Phase 4** — 三项创新 A 自适应、B SOS 优先级调度、C 图片预览优先＋完整原图恢复；确保全部经 Cable。

**Phase 5** — ASK/BFSK/BPSK、并发压力场景、Shannon/BER/FER/goodput/延迟实验，生成真实 JSON/CSV/PNG。

**Phase 6** — Streamlit UI、场景操作、实测日志、可靠重置，全部测试和简明文档；最终运行 `pytest`、Level1/Level2/Showcase CLI、quick experiments，并修复发现的问题。

### 必须具备的终端命令（根据项目结构实现等效命令，并在 README 保持一致）

```bash
python -m pip install -r requirements.txt
python scripts/run_level1.py
python scripts/run_level2.py
python scripts/run_showcase.py
python experiments/run_all.py --quick
pytest -q
streamlit run app.py
```

### 最终验收 Checklist（逐项亲自验证）

- [ ] 原版 Cable 被真正调用；真实波形实际通过 Cable；数据、ACK、Switch 转发、应用响应均遵循该约束。
- [ ] Level 1 短/长/中文文本、分片、CRC、噪声及 Shannon 参考实验可执行。
- [ ] Level 2 四 Host 星型、寻址、Switch 转发、并发消息、未知地址处理可执行。
- [ ] Level 3 可靠传输、Hamming/CRC、应用层请求响应、调制比较、并发至少有真实实现和测试。
- [ ] 创新 A：自动模式**真实**切换了物理层编码/参数，不是 UI 文本改变；固定模式对比结果可复现。
- [ ] 创新 B：拥塞状态下 SOS 在输出队列得到优先处理；有 FIFO 对照和延迟统计；普通业务不会永久饥饿。
- [ ] 创新 C：同一张图片的预览先到，原图后到；接收端根据网络真实接收数据呈现，SHA-256 一致。
- [ ] UI 的各按钮有作用且能重复运行；事件日志与数值由引擎产生。
- [ ] pytest、独立 Level1/Level2 Demo、完整 Showcase、`--quick` 实验能实际运行。
- [ ] README、协议文档、实验定义、要求映射表、5 分钟演示稿完备。

## 10. 输出与沟通规则

执行期间：可以在终端输出简短进度，但不要反复征询我的确认。遇到依赖/旧代码问题优先自行修复并继续；不隐藏任何失败。**只有全部功能写完并完成实际验收后才结束任务**。如果平台执行时间不足，可以阶段性保存所有代码与清晰 TODO，但必须如实列出未完成项，不允许将其假装为完成。

结束时请按下面顺序向我汇报：

1. 已实现模块清单（Level1/Level2/Level3/创新 A、B、C 分开说明）。
2. 项目关键文件目录与如何运行的命令。
3. 实际执行过的测试命令、通过/失败统计，失败与限制说明。
4. 实际运行过的 Demo/实验、输出的真实文件路径，以及主要结果（若尚未跑出则明确未测）。
5. 最终 5 分钟 PPT 推荐现场演示的具体点击顺序。
6. 仍需人工完成的事项（如录屏、上传 BB、PPT 美化、报告填写）。

**现在立即读取当前工作区并开始实施。不要只回复“我可以做到”或输出规划；请直接编写并运行真实代码。**
