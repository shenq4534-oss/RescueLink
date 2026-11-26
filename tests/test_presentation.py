"""Presentation acceptance tests exercise the real Cable and receive boundary."""
from pathlib import Path
import numpy as np
import pytest

from rescuelink.config import Config, MODES
from rescuelink.presentation import PointToPointSession, advance, image_snapshot, topology_html, timeline_html
from rescuelink.network.engine import Network
from rescuelink.simulation.scenarios import configure_showcase
from rescuelink.physical.channel import PhysicalLink
from rescuelink.physical.framing_phy import PREFIX_SAMPLES
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.application import Message


@pytest.mark.physical_channel
def test_level1_recording_chinese_cross_fragment_boundary():
    data=('跨片汉字与 UTF-8 / '+chr(0x1f6df))*19
    s=PointToPointSession(data.encode(),Config(noise=.15,payload=64))
    try:
        assert s.received is None
        s.step()
        assert s.received is None and not s.done
        while s.step():
            pass
        assert s.success and s.closed
        assert s.link.calls==len(s.parts)>1
        assert all(r['ok'] for r in s.records)
    finally:
        s.close()


def test_level1_failure_never_displays_sender_text():
    s=PointToPointSession(b'not secretly recovered'*25,Config(noise=10,payload=128),mode='Fast')
    try:
        while s.step():
            pass
        assert s.done and not s.success and s.received is None
    finally:
        s.close()


@pytest.mark.parametrize('scheme',['ASK','BFSK','BPSK'])
def test_waveform_is_the_actual_payload_not_fixed_preamble(scheme):
    link=PhysicalLink(Config(noise=.15),42,'payload-inspection')
    try:
        r=link.transmit(Frame(Kind.DATA,1,4,2,1,payload=b'payload').pack(),MODES['Balanced'],scheme)
        assert np.allclose(r['tx_payload'],link.cable.last_input_signal[PREFIX_SAMPLES:PREFIX_SAMPLES+512])
        assert np.allclose(r['rx_payload'],link.cable.last_output_signal[PREFIX_SAMPLES:PREFIX_SAMPLES+512])
    finally:
        link.close()


def test_recording_milestones_stop_at_real_receptions(tmp_path):
    with Network(Config(noise=.12,window=8,downlink_slowdown=2),tmp_path) as net:
        configure_showcase(net)
        assert image_snapshot(net)['original'] is None
        for target in ['preview','sos','image']:
            more,reached=advance(net,5000,target)
            assert reached
            if target=='preview':
                snap=image_snapshot(net)
                assert snap['preview'] is not None and snap['original'] is None
                assert net.events[-1].time==net.now
            if target=='sos':
                assert any(f.app_type=='SOS_ALERT' and f.delivered is not None for f in net.flows.values())
        snap=image_snapshot(net)
        assert snap['state']=='verified' and snap['original'] is not None
        # A second upload cannot reuse the old job's verified receiver pixels.
        from rescuelink.media.image_transfer import demo_image
        net.start_image(2,4,demo_image())
        assert image_snapshot(net)['original'] is None
        assert image_snapshot(net)['state']=='pending'


def test_dashboard_escapes_received_text(tmp_path):
    with Network(Config(noise=0),tmp_path) as net:
        assert '<script>' not in timeline_html(net)
        net.send(1,4,Message('TEXT','html',{},b'<script>alert(1)</script>'))
        net.run()
        net.log('decode_rejected',lane='down4',reason='<script>alert(1)</script>')
        assert '<script>' not in timeline_html(net)
        assert '&lt;script&gt;' in timeline_html(net)
        svg=topology_html(net)
        assert '中央交换机' in svg and 'DATA' not in timeline_html(net)
        assert 'payload' not in net.attempts[-1]
