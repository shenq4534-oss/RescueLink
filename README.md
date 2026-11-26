# RescueLink · 自适应可靠应急通信

GitHub：[shenq4534-oss/RescueLink](https://github.com/shenq4534-oss/RescueLink) · Public（按仓库所有者选择）。[自动化测试](https://github.com/shenq4534-oss/RescueLink/actions)

离线 Python 课程项目。实际生成采样载波，经老师原版 `Cable.transmit()` 加噪，再解调、纠错和校验。核心库不依赖 Streamlit 启动，不需要任何云服务。

|要求|实现|
|---|---|
|Level 1|字节/UTF-8、BPSK/ASK/BFSK、CRC-32、128/256 字节分片重组、噪声与容量参考实验|
|Level 2|A/B/C/D 四主机、唯一中央 Switch、8 根独立方向 Cable、按头部地址转发|
|Level 3|Stop-and-Wait / Go-Back-N、累计 ACK/NACK、超时重传、有限接收缓存、零窗口探测、Hamming SECDED、应用请求响应、多线程端口|
|创新 A|Fast/Balanced/Survival 自动保护、滞回、真实 Cable 返回的链路质量报告、固定策略对照|
|创新 B|按目的端口排队、SOS 帧优先、不抢占已开始帧、连续 3 个高优先帧后服务普通帧|
|创新 C|元信息→READY→预览→READY→原图→SHA-256→IMAGE_RECEIVED；所有阶段通过网络|

## 安装和运行

推荐 Python 3.11–3.13。在**本目录**执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/run_level1.py
python scripts/run_level2.py
python scripts/run_showcase.py
python experiments/run_all.py --quick
python -m pytest -q
streamlit run app.py
```

Windows 如不允许激活脚本，用 `.venv\Scripts\python.exe` 代替 `python`，界面命令为 `.venv\Scripts\python.exe -m streamlit run app.py`。macOS/Linux 激活命令为 `source .venv/bin/activate`。

需要与本次验收完全相同的依赖版本时，可改用 `python -m pip install -r requirements-lock.txt`（记录于 Windows / Python 3.12）。

`python main.py level1|level2|showcase` 是等效 CLI。更大样本实验：`python experiments/run_all.py --full --output outputs/full_experiments`。默认启动 UI 不重新执行实验。

## 界面演示

1. 左侧选择 Auto、BPSK、Priority、GBN 和窗口，点击“应用配置 / 重置”。编码由保护策略明确控制：Fast 关闭 FEC，另外两档开启。
2. 输入中文并发送；接收端展示真实恢复的文本；“查询状态”展示返回的 STATUS_RESPONSE。
3. 点击“开始图片上传”（不选文件使用原创示例），点击单步或继续。预览到达后可暂停查看。
4. 图片正在发送时点击“触发 SOS”，在“链路与事件”查看入队、physical_send、application_received 和 SOS 时延。
5. “运行完整 Demo”重置并预置输入、噪声变化和 SOS 到达时间；12 个事件/刷新，支持暂停、单步、停止、重置。先收到预览，在原图发送中模拟22s生成 SOS，噪声在32s升高、55s降低。
6. 接收端完成原图后显示 SHA-256；“已计算实验”显示离线结果及生成时间。

### 底层过程与 Cable 调用追踪

页面顶部“演示视图”选择 **底层实验室**，输入文字（如 `SOS：请救援`），选每片16/32字节，再点“运行逐层实验”。选择任一分片后，依次查看：

1. **字节→比特**：UTF-8 十六进制、逐字节二进制、发送端正文。
2. **成帧→编码**：src/dst、消息/片段编号、Header/正文/CRC、编码前后长度与位串。
3. **调制→Cable**：正文附近的真实 TX 与 Cable 返回 RX 波形；原版 Cable 文件 SHA-256、调用次数、原版对象保存的输入/输出一致性。
4. **解调→校验**：从接收波形独立解出的 PHY 参数、编码位错误位置、纠错结果、CRC 结果和实际收到的正文。

实验快照保存在当前会话，可切换步骤、分片并下载完整追踪 JSON；控件改变不会改写旧快照，重新点击运行才产生新数据。底层实验室是直接点对点链路，不自动重传，便于观察坏帧被拒收。

切回 **应急网络**，发送一条短消息后，在“逐帧追踪”按 message_id/sequence 对照 `up1→down4` 等路径，以及返回 ACK。有效上行接收帧哈希应等于对应下行发送帧哈希。界面只保留最近80次发送的详细快照；紧凑事件记录仍保留全部发送。追踪仅为观测，不参与解码与应用交付；默认 CLI/实验不采集这些详细快照。

反向验证：`python -m pytest -vv tests/test_trace.py`。包括原版调用捕获、返回波形替换后恢复替换内容、全零返回导致无法送达、仅阻断目的下行导致无法送达。受控替换/阻断只用于自动化测试，不作为 Cable 真实噪声实验。哈希用于关联观测，不是独立的防篡改认证；应结合源码与可复现实验展示。

Wireshark 捕获网卡或回环接口的数据包；当前 Host/Switch 是进程内模拟节点，不能直接捕获 `Cable.transmit()` 的 NumPy 数组。抓到 Streamlit 的 HTTP/WebSocket 只说明浏览器连接了界面，不能证明业务经过老师 Cable。两台电脑通信需要另加实际 socket 传输层，并继续保留 Cable 调制/解调路径，不能用 TCP 发送原文代替课程链路。

## 文件与职责

```text
cable.py                  老师原版，不修改
app.py / main.py          界面 / CLI
rescuelink/physical/      位、手写调制、SECDED、独立 PHY 头、Cable 适配
rescuelink/protocol/      二进制帧、CRC、分片、可靠传输状态、应用解析
rescuelink/network/       端口队列、交换机、主机、自适应、线程、统一引擎
rescuelink/media/         图片检查、预览、接收字节校验和安全落盘
rescuelink/simulation/    时钟、指标、输入场景
tests/                    单元、原版物理信道、端到端、界面验收
experiments/run_all.py    集中实验入口，减少重复脚本
docs/                     架构、协议、实验、要求映射、5 分钟讲稿
outputs/                  实测 JSON/CSV/PNG、事件和接收文件
```

课程最新版来自 `Downloads/README.md`，保存在 `course/README.latest.md`，含星型拓扑、多线程及 Presentation Guide。按给定路径与 Downloads/Desktop 查找未找到字面名 `README(1).md`。原始依赖保存在 `course/requirements.original.txt`。Master Prompt 已完整保留，课程要求优先；未把文档中的文字当作额外发布授权。

## 复现与真实边界

详见 [协议](docs/PROTOCOL.md)、[实验](docs/EXPERIMENTS.md)、[实测验收](docs/VALIDATION.md)。所有网络时间来自同一个事件时钟；Python 运行时间只代表准备成本。PHY 理想同步、共享符号边界和相位；无载波捕获、时钟漂移、冲突、无线/MIMO。下行时钟倍率用于可重复的输出拥塞。

链路质量报告本身也占真实 Cable 带宽，保护头较长，因此此教学系统的效率低于实际网络。极强噪声、重试上限、未知地址会真实失败。CRC 后剩余多比特错误不承诺修复。图片最大 512 KiB、400 万像素；应用消息最大 2 MiB。消息 ID 在单个引擎中不复用，重置创建新会话。

UI 使用有界分步推进，暂停时仍可提交新消息，避免后台线程失控。物理端口有独立线程，确定性事件调度器按事件顺序等待计算；不声称拥有并行 RF 仿真的 CPU 加速。原版 Cable 的全局 NumPy RNG 用短临界区隔离，不改变加噪模型。

## 两人协作

建议一人负责 physical/protocol，一人负责 network/media/UI；共同检查 experiments 与 tests。每个功能用独立分支和 PR，合并前运行 pytest 和 quick 实验。见 [协作说明](docs/COLLABORATION.md)。当前仓库为 **Public**；所有者可以在 Settings → Collaborators 中邀请搭档获得写入权限。

课程材料期限：代码、PPT 和其他材料 **12 月 18 日 14:00** 上传 BB；报告 **12 月 28 日 23:59**；展示 **5 分钟**。本工程未代为上传 BB。
