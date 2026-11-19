# 要求映射

|要求|实现位置|命令 / 测试|界面位置|
|---|---|---|---|
|原版 Cable、真实波形|physical/channel.py PhysicalLink|test_original_cable_all_modulations_and_modes；原版 SHA见 VALIDATION|链路与事件 TX/RX|
|短/长/中文/任意字节|bits.py、scenarios.level1|run_level1.py；test_level1_noise_fragmentation|发送文本|
|CRC、严格 Header|protocol/frame.py Frame|test_crc_header_and_payload、test_bounds|损坏帧 / 日志|
|分片重组/重复/乱序|fragmentation.Reassembler|test_reassembly_out_of_order_duplicate_missing|事件 sequence / 接收内容|
|星型4Host/8方向|network/engine.py、switch.py、host.py|run_level2.py；test_star_forward_ack_response|拓扑 / 端口表|
|未知地址拒绝|Network._arrive|test_unknown_destination_failure|失败原因 / 日志|
|每次转发/ACK/响应经 Cable|_dispatch / _arrive / _control / _application|test_star_forward_ack_response|physical_send frame_type|
|Hamming SECDED|physical/coding.py|test_secded_exhaustive（16×所有单错/双错）|纠正/不可纠正码字|
|Stop-and-Wait / GBN|SendFlow、_pump、_receive_ack|test_reliable_ack_loss_no_duplicate 两模式|侧栏可靠传输|
|丢包、NACK、超时、上限|_timeout、_receive_data|test_data_loss_gbn_and_nack、test_retry_exhaustion_no_fake_delivery|重传、失败状态|
|有限接收缓存 / 零窗口|Host.rx_pending、_consume、PROBE|test_zero_window_probe_recovery|window_advertised 事件|
|应用解析与请求响应|protocol/application.py、_application|test_malformed_app_and_image、test_star_forward_ack_response|查询状态、SOS_ACK|
|创新 A 反馈自适应/滞回|AdaptiveController、LINK_REPORT|test_adaptive_hysteresis、test_adaptive_over_real_feedback_cables|实际模式、反馈、切换历史|
|创新 A 固定策略对照|experiments.adaptive|run_all.py --quick；results.adaptive/phases|已计算实验 adaptive.png|
|创新 B 非抢占优先/防饥饿|scheduler.PortQueue、_dispatch|test_priority_fairness_and_fifo、test_actual_congestion_priority|开始图片上传→触发SOS|
|创新 B 多种子公平对照|experiments.scheduling|FIFO/Priority down4 backlog、均值/P95|scheduling.png / SOS延迟|
|创新 C 真预览/原图/SHA|image_transfer.py、_image_next|test_image_received_bytes_hash_order、test_image_missing_no_success|接收端预览、原图、SHA|
|仅原图/预览对照|experiments.progressive|results.progressive 首次可用时间和额外字节|预览优先复选框|
|ASK/BFSK/BPSK|physical/modulation.py|9组原版 Cable 无噪声测试、E3|调制选择 / 图表|
|多线程并发/退出|PhysicalLink.worker、Runner、RLock|test_concurrent_submissions_cleanup_reproducible、test_runner_lifecycle|停止 / 重置|
|固定种子重现|Clock、独立方向RNG|test_deterministic_scenario_trace；固定到达实验|种子输入|
|统一时间/传播/占用|Clock、PhysicalLink、_dispatch|test_original_cable_all_modulations_and_modes；attempts start/end/arrival|模拟时间，非CPU秒|
|Shannon/BER/FER/吞吐|simulation/metrics.py、experiments/run_all.py|E2–E7 JSON/CSV/PNG|已计算实验|
|可用 UI / rerun / 清理|app.py|test_ui_send_step_reset、test_ui_showcase_and_response|运行/暂停/继续/停止/复位|
|5分钟中文讲稿/录屏脚本|docs/PRESENTATION_5MIN.md|3个 scripts 入口|完整 Demo|

测试标记 `unit / integration / physical_channel` 可分别筛选，例如 `python -m pytest -m physical_channel -q`。界面 AppTest 不需要浏览器或已运行的 Streamlit 服务。
