"""Real Cable call observations; fault cases below are explicit controlled tests."""
import hashlib
from pathlib import Path
import numpy as np
import pytest
from cable import Cable
from rescuelink.config import Config, MODES
from rescuelink.physical.channel import PhysicalLink
from rescuelink.physical.framing_phy import encode
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.application import Message
from rescuelink.network.engine import Network
from rescuelink.simulation.scenarios import level1


@pytest.mark.physical_channel
def test_trace_observes_original_cable_call(monkeypatch):
    original = Cable.transmit
    observed = []
    def spy(cable, signal):
        received = original(cable, signal)
        observed.append((signal.copy(),received.copy()))
        return received
    monkeypatch.setattr(Cable,"transmit",spy)
    link = PhysicalLink(Config(noise=.2),42,"audit",capture=True)
    try:
        frame = Frame(Kind.DATA,1,4,2,1,payload="SOS 中文".encode())
        result = link.transmit(frame.pack(),MODES["Balanced"])
        trace = result["trace"]
        assert len(observed)==link.calls==1 and result["ok"]
        assert trace["cable_input_matches"] and trace["cable_output_matches"]
        tx,rx = observed[0]
        assert len(tx)>len(frame.pack())*8
        assert trace["waveform_sha256_tx"]==hashlib.sha256(tx.astype("<f8").tobytes()).hexdigest()
        assert trace["waveform_sha256_rx"]==hashlib.sha256(rx.astype("<f8").tobytes()).hexdigest()
        assert trace["cable_source_sha256"]==hashlib.sha256(Path("cable.py").read_bytes()).hexdigest()
        assert bytes.fromhex(trace["payload_hex_rx"])==frame.payload
        assert trace["frame_sha256_rx"]==trace["frame_sha256_tx"]
    finally:
        link.close()


@pytest.mark.integration
def test_receiver_uses_returned_waveform_not_original_bytes(monkeypatch):
    # Controlled signal substitution, not a noise experiment: encode a different
    # valid frame and run THAT waveform through original Cable. Receiver must
    # recover the substituted frame, not copy the original sender's raw bytes.
    original = Cable.transmit
    sent = Frame(Kind.DATA,1,4,2,1,payload=b"ORIGINAL")
    actual = Frame(Kind.DATA,1,4,2,1,payload=b"RECEIVED")
    actual_wave,_ = encode(actual.pack(),MODES["Balanced"])
    def substitute(cable, signal):
        return original(cable,actual_wave)
    monkeypatch.setattr(Cable,"transmit",substitute)
    link = PhysicalLink(Config(noise=0),42,"substitution-test",capture=True)
    try:
        result = link.transmit(sent.pack(),MODES["Balanced"])
        assert result["ok"] and Frame.unpack(result["raw"]).payload==actual.payload
        assert result["raw"]!=sent.pack()
        assert result["trace"]["payload_hex_rx"]==actual.payload.hex()
        assert not result["trace"]["cable_input_matches"]
        assert result["trace"]["frame_sha256_tx"]!=result["trace"]["frame_sha256_rx"]
    finally:
        link.close()


@pytest.mark.integration
def test_zero_cable_output_cannot_deliver(monkeypatch):
    original = Cable.transmit
    calls=[]
    def block(cable, signal):
        calls.append(1)
        received=original(cable,signal)
        return np.zeros_like(received)  # Explicit test injection after real Cable.
    monkeypatch.setattr(Cable,"transmit",block)
    result=level1(b"Never echo this",noise=0,capture=True)
    assert calls and not result["success"] and result["received_hex"] is None
    assert not result["records"][0]["ok"]
    assert result["records"][0]["trace"]["payload_hex_rx"] is None


@pytest.mark.integration
def test_switch_downlink_is_required(tmp_path):
    with Network(Config(noise=0,max_retries=1),tmp_path,capture=True) as n:
        original=n.links["down4"].cable.transmit
        def block(signal):
            return np.zeros_like(original(signal))
        n.links["down4"].cable.transmit=block  # Only the destination's real downlink is blocked.
        mid=n.send(1,4,Message("TEXT","blocked",{},b"secret"))
        n.run()
        assert n.flows[mid].status=="failed" and not n.hosts[4].received
        assert any(a["lane"]=="up1" and a["ok"] and a["frame_type"]=="DATA" for a in n.attempts)
        assert all(not a["ok"] for a in n.attempts if a["lane"]=="down4")


@pytest.mark.physical_channel
@pytest.mark.parametrize("scheme",["BPSK","ASK","BFSK"])
def test_level1_trace_utf8_fragment_reassembly(scheme):
    data="中文救援".encode()*6
    r=level1(data,noise=0,payload=16,scheme=scheme,capture=True)
    assert r["success"] and bytes.fromhex(r["received_hex"])==data
    assert r["fragments"]==r["cable_calls"]>1
    assert all(a["trace"]["phy_header_rx"]["modulation"]==scheme for a in r["records"])
    assert all(a["trace"]["coded_bits_tx"]==a["trace"]["coded_bits_rx"] for a in r["records"])


@pytest.mark.integration
def test_network_trace_correlates_both_hops_and_is_bounded(tmp_path):
    with Network(Config(noise=0,window=4),tmp_path,capture=True) as n:
        mid=n.send(2,4,Message("TEXT","trace",{},b"x"*4000))
        n.run()
        assert n.flows[mid].delivered is not None
        up=next(a for a in n.attempts if a["lane"]=="up2" and a["frame_type"]=="DATA")
        down=next(a for a in n.attempts if a["lane"]=="down4" and a["frame_type"]=="DATA")
        assert up["frame_sha256_rx"]==down["frame_sha256_tx"]==down["frame_sha256_rx"]
        assert n.stats["physical_transmissions"]>80 and len(n.traces)==80
        assert all("trace" not in a for a in n.attempts)


@pytest.mark.unit
def test_detailed_capture_is_opt_in():
    result=level1(b"hello",noise=0)
    assert "trace" not in result["records"][0]
