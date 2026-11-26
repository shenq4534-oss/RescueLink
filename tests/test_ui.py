from streamlit.testing.v1 import AppTest
from pathlib import Path

def button(app,label):
    return next(b for b in app.button if b.label==label)

def test_ui_send_step_reset():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=20).run()
    assert not app.exception
    button(app,"发送文本").click().run()
    assert not app.exception
    for _ in range(8): button(app,"单步推进 12 个事件").click().run()
    net=app.session_state["net"]
    assert any(r["message"].type=="TEXT" for r in net.hosts[4].received)
    button(app,"开始图片上传").click().run()
    button(app,"触发 SOS").click().run()
    assert not app.exception
    button(app,"停止任务").click().run()
    assert app.session_state["net"].closed
    button(app,"应用配置 / 重置").click().run()
    assert not app.exception
    assert not app.session_state["net"].flows
    app.session_state["net"].close()

def test_ui_showcase_and_response():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=20).run()
    button(app,"查询状态").click().run()
    app.session_state["net"].run()
    assert app.session_state["net"].hosts[1].received[0]["message"].type=="STATUS_RESPONSE"
    button(app,"运行完整 Demo").click().run()
    app.session_state["net"].run()
    app.run()
    assert not app.exception
    assert any(i["verified"] for i in app.session_state["net"].hosts[4].images.values())
    assert app.session_state["net"].summary()["mode_changes"]
    app.session_state["net"].close()

def test_recording_pages_and_level1_real_reassembly():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    next(r for r in app.radio if r.label=="展示页面").set_value("Level 1 · 点对点").run()
    button(app,"开始点对点传输").click().run()
    for _ in range(20):
        if app.session_state["p2p"].done:
            break
        button(app,"单步发送一个分片").click().run()
    assert not app.exception
    assert app.session_state["p2p"].success
    assert app.session_state["p2p"].link.calls>1
    next(r for r in app.radio if r.label=="展示页面").set_value("Level 2 · 星形转发").run()
    button(app,"载入 Level 2 场景").click().run()
    app.session_state["net"].run()
    app.run()
    assert not app.exception
    assert app.session_state["net"].summary()["delivered"]==3
    next(r for r in app.radio if r.label=="展示页面").set_value("实验与对照").run()
    assert not app.exception
    app.session_state["net"].close()

def test_live_noise_is_applied_without_resetting_flows():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30).run()
    button(app,"开始图片上传").click().run()
    net=app.session_state["net"]
    button(app,"加入干扰 σ=0.85").click().run()
    assert app.session_state["net"] is net
    assert all(link.cable.noise_level==.85 for link in net.links.values())
    button(app,"恢复链路 σ=0.12").click().run()
    assert all(link.cable.noise_level==.12 for link in net.links.values())
    assert net.flows and not app.exception
    net.close()
