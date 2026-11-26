# 实际验收报告

生成于实验记录 2026-11-19T09:02:11.209207+00:00（UTC）。运行环境 Windows / Python 3.12；安装版本见 requirements-lock.txt。以下数字来自已保存的 JSON 和 pytest XML，不是预设输出。

## 运行命令和结果

|命令|结果|
|---|---|
|python -m pip install -r requirements.txt / pip check|依赖已安装，pip check 无冲突；lock保留实测版本|
|python -m pytest -q --junitxml=outputs/validation/pytest.xml|43/43 通过，0 失败，0 跳过；12.19 CPU/墙钟秒是测试准备时间，不是网络时间|
|python scripts/run_level1.py|10/10 用例通过；最多12个分片|
|python scripts/run_level2.py|3/3 应用消息交付（含状态响应），24次真实物理发送|
|python scripts/run_showcase.py|9/9 应用消息交付，9确认，0失败，6次DATA重传|
|python experiments/run_all.py --quick|E1–E7与预览对照完成，51行标量结果，7张PNG，原始JSON/CSV与详细链路日志|
|python -m streamlit run app.py --server.headless true|服务实际启动；浏览器看到网络接收图片与SHA校验；AppTest验证文本、状态、图片、SOS、完整Demo、停止、重置|

`--full` 的执行路径已提供，本次没有运行全量实验。GitHub Actions 已在 Ubuntu / Python 3.12 上成功执行安装依赖和 pytest：[验收代码提交 a1068fe 的 CI](https://github.com/shenq4534-oss/RescueLink/actions/runs/44499496506)。最新状态见仓库 Actions 页面。

## Showcase

预览真实可用 T=18.794s；SOS生成22s、实际应用送达28.501s（延迟6.501s）；原图实际完成 T=238.869s；SHA-256 与输入一致。

网络直到所有确认和物理反馈结束为 910.671s。保守 RTO 和一次丢失的确认会产生长等待；不能把原图应用完成时刻与整个网络最终确认时刻混称。模式切换6次，实际方向和原因见 summary/events。

## 自适应（相同外生噪声序列）

|Seed|策略|应用成功率|Goodput bit/s|重传|完成模拟秒|模式切换|
|---|---|---|---|---|---|---|
|42|Fixed Fast|100.0%|166.39|10|221.55|0|
|42|Fixed Survival|100.0%|205.64|0|179.26|0|
|42|Auto|100.0%|175.15|6|210.47|5|
|43|Fixed Fast|100.0%|166.39|10|221.55|0|
|43|Fixed Survival|100.0%|205.64|0|179.26|0|
|43|Auto|100.0%|175.15|6|210.47|5|

Auto 比固定 Fast 少部分重传，但本场景固定 Survival 更高效；不宣称 Auto 始终最优。

## SOS 调度

|Seed|调度|SOS均值秒|SOS P95秒|图片完成秒|down4队列峰值|
|---|---|---|---|---|---|
|42|FIFO|32.531|40.901|132.959|28|
|42|Priority|9.327|12.381|160.067|21|
|43|FIFO|32.531|40.901|132.959|28|
|43|Priority|9.327|12.381|160.067|21|
|44|FIFO|32.531|40.901|132.959|28|
|44|Priority|9.327|12.381|160.067|21|

Priority 有真实 backlog，降低 SOS 等待，但延长普通图片完成时间。每个 seed 中3个SOS；这里列各seed内统计，小样本不能解释为一般置信保证。

## 图片首次可用与传输效率

|策略|首次图像秒|原图完成秒|预览额外字节|
|---|---|---|---|
|仅原图|34.295|34.295|0|
|预览优先|10.138|42.669|502|

|传输协议|Goodput bit/s|真实重传|
|---|---|---|
|Stop-and-Wait|440.91|0|
|GBN|830.42|0|

## 高噪声真实失败

|noise|固定Fast应用交付率|重试耗尽消息|
|---|---|---|
|0|100.0%|0|
|0.3|100.0%|0|
|0.7|0.0%|3|
|1.0|0.0%|3|
|1.4|0.0%|3|

这些是实验观测的失败，不是 pytest 失败；框架没有伪造恢复。

## 文件与后续事项

- outputs/validation/pytest.xml：本次测试证据。
- outputs/level1/results.json、outputs/level2/、outputs/showcase/：独立 Demo 的真实记录。
- outputs/experiments/results.json、results.csv、*.png：详细实验配置与结果。
- 原版 Cable SHA-256：`bf668db7212f485aef14c8878c61c28943074b2ec57f19013039b169b1a5b1b7`；与 Desktop/project 原文件核对一致。
- GitHub：已发布至 https://github.com/shenq4534-oss/RescueLink ，按用户选择保持 Public。本地 origin 已改为该仓库；验收代码 a1068fe 已核对远程提交一致，Ubuntu CI 成功。搭档尚未邀请。
- 尚需人工：搭档账号与邀请、真实录屏、PPT排版、报告、BB上传。没有制作正式PPT或代为提交。
- 理想同步、冗长保护头、反馈开销、保守RTO、没有无线/MIMO、Full未跑等限制见 README/PROTOCOL/EXPERIMENTS。

## 2026-11-26：底层实验室与因果验证补充

新增可选的真实物理调用追踪、四步骤点对点教学界面、星型网络双跳帧关联；原版 cable.py 未修改，SHA-256 仍与课程原文件一致。正式噪声实验继续使用原模型，详细快照不参与接收解码。

- 全套测试：`python -m pytest -q -p no:cacheprovider`，53 项通过。
- 新增追踪和界面检查：`python -m pytest -vv -p no:cacheprovider tests/test_trace.py tests/test_ui.py::test_ui_layer_lab_and_four_steps --junitxml=outputs/validation/trace_inspection.xml`，10 项通过（是上述53项中的子集）。
- 原版调用 spy 捕获实际输入/输出，核对样本、哈希、调用数。
- 受控信号替换：接收端恢复替换波形中的正文，不会回显原发送字节。
- 受控全零返回 / 目的下行阻断：消息无法交付。以上是明确的故障注入测试，不是自然噪声测量。
- `outputs/level1_trace_demo.json`：当次真实运行的90字节中文文本，6片、6次原版 Cable 调用，恢复成功，包含各阶段观测与完整分片追踪。
- Streamlit 服务在本机启动，教学界面四步骤通过 AppTest。该轮浏览器控制服务不可用，未完成浏览器截图验收。

哈希和日志用于关联程序观测，不提供独立防篡改认证；讲解时应结合源码和反向验证。双电脑 socket 传输及 Wireshark 现场抓包不是当前实现范围。
