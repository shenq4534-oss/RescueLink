import pytest
from rescuelink.config import Config
from rescuelink.network.engine import Network
from rescuelink.protocol.application import Message
from rescuelink.protocol.frame import Kind

pytestmark=pytest.mark.integration

def test_star_forward_ack_response(tmp_path):
    with Network(Config(noise=0),tmp_path) as n:
        n.send(1,4,Message("TEXT","x",{},"中文".encode()*200))
        n.send(3,2,Message("STATUS_QUERY","y",{}))
        n.run()
        assert len(n.links)==8 and n.summary()["failed"]==0
        assert n.hosts[4].received[0]["message"].body == "中文".encode()*200
        assert n.hosts[3].received[0]["message"].type == "STATUS_RESPONSE"
        assert any(a["lane"]=="up1" and a["frame_type"]=="DATA" for a in n.attempts)
        assert any(a["lane"]=="down4" and a["frame_type"]=="DATA" for a in n.attempts)
        assert any(a["lane"]=="up4" and a["frame_type"]=="ACK" for a in n.attempts)
        assert any(a["lane"]=="down1" and a["frame_type"]=="ACK" for a in n.attempts)
        assert sum(l.calls for l in n.links.values())==len(n.attempts)

def test_unknown_destination_failure(tmp_path):
    with Network(Config(noise=0,max_retries=1),tmp_path) as n:
        mid=n.send(1,99,Message("TEXT","bad",{},b"secret"))
        n.run()
        assert n.flows[mid].status=="failed"
        assert n.stats["unknown_destination"]>0
        assert not any(h.received for h in n.hosts.values())

@pytest.mark.parametrize("transport",["Stop-and-Wait","GBN"])
def test_reliable_ack_loss_no_duplicate(transport,tmp_path):
    dropped=[False]
    def fault(lane,frame,attempt):
        if lane=="down1" and frame.kind==Kind.ACK and not dropped[0]:
            dropped[0]=True
            return True
        return False
    with Network(Config(noise=0,transport=transport),tmp_path,fault=fault) as n:
        n.send(1,4,Message("TEXT","ackloss",{},b"abc"))
        n.run()
        assert n.stats["retransmissions"]>=1
        assert len(n.hosts[4].received)==1
        assert n.summary()["failed"]==0

def test_data_loss_gbn_and_nack(tmp_path):
    dropped=[False]
    def fault(lane,f,attempt):
        if lane=="down4" and f.kind==Kind.DATA and f.sequence==1 and not dropped[0]:
            dropped[0]=True; return True
        return False
    with Network(Config(noise=0,window=4),tmp_path,fault=fault) as n:
        n.send(2,4,Message("TEXT","loss",{},b"a"*1600))
        n.run()
        assert n.stats["NACK"]>0 and n.stats["retransmissions"]>0
        assert len(n.hosts[4].received)==1 and n.summary()["failed"]==0

def test_retry_exhaustion_no_fake_delivery(tmp_path):
    with Network(Config(noise=0,max_retries=2),tmp_path,
                 fault=lambda lane,f,i: f.kind==Kind.DATA and lane=="down4") as n:
        mid=n.send(1,4,Message("TEXT","never",{},b"lost"))
        n.run()
        assert n.flows[mid].status=="failed" and not n.hosts[4].received

def test_zero_window_probe_recovery(tmp_path):
    def fault(lane,f,i):
        return f.kind==Kind.WINDOW_UPDATE and f.window>0
    with Network(Config(noise=0,window=4,rx_capacity=1,process_delay=5),tmp_path,fault=fault) as n:
        n.send(1,4,Message("TEXT","window",{},b"x"*800))
        # Only proactively generated recovery notifications are lost; allow PROBE replies later.
        # Drop first three updates, then recovery is observable on the physical path.
        count=[0]
        def selective(lane,f,i):
            if f.kind==Kind.WINDOW_UPDATE and f.window>0 and count[0]<3:
                count[0]+=1; return True
            return False
        n.fault=selective
        n.run()
        assert any(e.kind=="window_advertised" and e.details["window"]==0 for e in n.events)
        assert n.stats["PROBE"]>0
        assert n.summary()["failed"]==0 and len(n.hosts[4].received)==1
        assert max(h.rx_pending for h in n.hosts.values())==0
