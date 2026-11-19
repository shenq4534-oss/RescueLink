from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from PIL import Image
import hashlib
import threading
import pytest
from rescuelink.config import Config
from rescuelink.network.engine import Network
from rescuelink.network.adaptive import AdaptiveController
from rescuelink.network.scheduler import PortQueue
from rescuelink.media.image_transfer import demo_image, prepare_image
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.application import Message
from rescuelink.network.concurrent import Runner

@pytest.mark.unit
def test_adaptive_hysteresis():
    a=AdaptiveController()
    for _ in range(6): a.feedback(0)
    assert a.mode=="Survival"
    for _ in range(16): a.feedback(2)
    assert a.mode=="Fast"
    fixed=AdaptiveController("Fixed Fast")
    for _ in range(10): fixed.feedback(0)
    assert fixed.mode=="Fast"

@pytest.mark.integration
def test_adaptive_over_real_feedback_cables(tmp_path):
    with Network(Config(noise=1.05),tmp_path) as n:
        for i in range(8): n.send(1,4,Message("TEXT",str(i),{},b"a"*400),at=i*5)
        n.schedule(45,n.set_noise,0)
        for i in range(8,22): n.send(1,4,Message("TEXT",str(i),{},b"b"*100),at=50+(i-8)*3)
        n.run()
        assert n.summary()["mode_changes"]
        assert any(a["mode"]=="Survival" and a["frame_type"]=="DATA" for a in n.attempts)
        assert any(a["frame_type"]=="LINK_REPORT" for a in n.attempts)
        assert any(e.kind=="mode_changed" and e.details["new"]=="Fast" for e in n.events)

@pytest.mark.unit
def test_priority_fairness_and_fifo():
    q=PortQueue()
    q.push((Frame(Kind.DATA,1,4,2,1),0))
    for i in range(12): q.push((Frame(Kind.DATA,3,4,0,2+i),0))
    selected=[q.pop()[0].priority for _ in range(4)]
    assert selected==[0,0,0,2]
    fifo=PortQueue("FIFO")
    fifo.push((Frame(Kind.DATA,1,4,2,1),0)); fifo.push((Frame(Kind.DATA,3,4,0,2),1))
    assert fifo.pop()[0].priority==2

def congestion(policy,tmp_path,seed=42):
    with Network(Config(noise=0,window=12,scheduler=policy,downlink_slowdown=3,seed=seed),tmp_path) as n:
        n.start_image(2,4,demo_image(),progressive=False)
        n.send(1,4,Message("TEXT","load",{},b"load"*600),at=8)
        sos=n.send(3,4,Message("SOS_ALERT","sos",{},b"SOS"),0,at=12)
        n.run()
        f=n.flows[sos]
        assert f.delivered is not None
        assert n.queues["down4"].peak>1
        assert any(i["verified"] for i in n.hosts[4].images.values())
        return f.delivered-f.generated,n.summary()

@pytest.mark.integration
def test_actual_congestion_priority(tmp_path):
    fifo,_=congestion("FIFO",tmp_path/"fifo")
    priority,_=congestion("Priority",tmp_path/"priority")
    assert priority<fifo

@pytest.mark.integration
@pytest.mark.parametrize("progressive",[True,False])
@pytest.mark.parametrize("image_format",["PNG","JPEG"])
def test_image_received_bytes_hash_order(tmp_path,progressive,image_format):
    data=demo_image()
    if image_format=="JPEG":
        buf=BytesIO()
        Image.open(BytesIO(data)).save(buf,"JPEG",quality=65)
        data=buf.getvalue()
    with Network(Config(noise=.2),tmp_path) as n:
        n.start_image(2,4,data,progressive)
        n.run()
        state=next(iter(n.hosts[4].images.values()))
        assert state["verified"] and state["original"]==data
        assert hashlib.sha256(state["original"]).hexdigest()==state["meta"]["sha256"]
        if progressive: assert state["preview_time"]<state["full_time"]
        else: assert state["preview"] is None
        assert any(r["message"].type=="IMAGE_RECEIVED" for r in n.hosts[2].received)

@pytest.mark.integration
def test_image_missing_no_success(tmp_path):
    with Network(Config(noise=0,max_retries=1),tmp_path,
                 fault=lambda lane,f,i: lane=="down4" and f.kind==Kind.DATA and f.priority==2) as n:
        n.start_image(2,4,demo_image())
        n.run()
        state=next(iter(n.hosts[4].images.values()))
        assert state["preview"] is not None and state["original"] is None and not state["verified"]

@pytest.mark.integration
def test_concurrent_submissions_cleanup_reproducible(tmp_path):
    results=[]
    for run in range(2):
        with Network(Config(noise=.2),tmp_path/str(run)) as n:
            def submit(i): return n.send(i%3+1,4 if i%2 else (i%3+1)%4+1,Message("TEXT",str(i),{},bytes([i])*80),at=i*.01)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(submit,range(24)))
            n.run()
            assert sum(len(h.received) for h in n.hosts.values())==24
            assert n.summary()["failed"]==0
            results.append(n.summary()["delivered"])
        assert not any(t.name.startswith("cable-") for t in threading.enumerate())
    assert results==[24,24]

@pytest.mark.unit
def test_malformed_app_and_image():
    for raw in (b"",b"\x00\x00\xff\xff{}",b"\x00\x00\x00\x02{}"):
        with pytest.raises(ValueError): Message.unpack(raw)
    with pytest.raises(ValueError): prepare_image(b"garbage","bad")

@pytest.mark.integration
def test_deterministic_scenario_trace(tmp_path):
    traces=[]
    for _ in range(2):
        with Network(Config(seed=97,noise=.6),tmp_path) as n:
            n.send(1,4,Message("TEXT","same",{},b"fixed payload"*40))
            n.send(3,2,Message("STATUS_QUERY","query",{}),at=2)
            n.run()
            traces.append((n.attempts,[e.asdict() for e in n.events]))
    assert traces[0]==traces[1]

@pytest.mark.integration
def test_runner_lifecycle(tmp_path):
    n=Network(Config(noise=0),tmp_path)
    runner=Runner(n)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: runner.submit(i%3+1,4,Message("TEXT",str(i),{},b"hello")),range(12)))
    runner.start()
    runner.commands.join()
    # Lock arbitrates with the runner; both consume the same deterministic event queue.
    n.run()
    runner.stop()
    assert not runner.thread.is_alive() and runner.error is None
    assert len(n.hosts[4].received)==12
