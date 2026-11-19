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
