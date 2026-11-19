from pathlib import Path
from rescuelink.config import Config, MODES
from rescuelink.network.engine import Network
from rescuelink.physical.channel import PhysicalLink
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.fragmentation import split, Reassembler
from rescuelink.protocol.application import Message
from rescuelink.media.image_transfer import demo_image

def level1(data="Hello · 救援链路".encode(), noise=.15, payload=128, scheme="BPSK"):
    config = Config(noise=noise)
    link = PhysicalLink(config, 42, "point-to-point")
    parts = split(data, payload)
    rx = Reassembler(len(parts))
    restored = None
    records = []
    try:
        for i, part in enumerate(parts):
            frame = Frame(Kind.DATA, 1, 4, 2, 1, i, i, len(parts), payload=part)
            r = link.transmit(frame.pack(), MODES["Balanced"], scheme)
            records.append({k:v for k,v in r.items() if k not in ("raw", "tx", "rx")})
            if r["ok"]:
                f = Frame.unpack(r["raw"])
                restored = rx.add(f.index, f.count, f.payload)
        duration = sum(r["duration"]+r["propagation"] for r in records)
        return dict(success=restored == data, fragments=len(parts), received_hex=restored.hex() if restored is not None else None,
                    goodput_bps=(len(data)*8/duration if restored == data else 0), simulated_seconds=duration,
                    records=records)
    finally:
        link.close()

def level2(output="outputs/level2"):
    with Network(Config(noise=.1), Path(output)/"received") as net:
        net.send(1,4,Message("TEXT","a-d",{},"A→D 状态正常".encode()))
        net.send(3,2,Message("STATUS_QUERY","c-b",{}))
        net.run()
        net.export(output)
        return net.summary()

def configure_showcase(net, image=None, progressive=True):
    image_id = net.start_image(2,4,image or demo_image(), progressive)
    # Arrival schedules are inputs. Outputs always derive from Cable receptions.
    net.schedule(18.0, net.send, 1,4,Message("TEXT","load",{},b"sensor block "*140),2)
    net.schedule(22.0, net.send, 3,4,Message("SOS_ALERT","sos",{},"SOS：四区需要救援".encode()),0)
    net.schedule(32.0, net.set_noise, .85)
    net.schedule(55.0, net.set_noise, .12)
    return image_id

def showcase(output="outputs/showcase", config=None):
    with Network(config or Config(noise=.12, window=8, downlink_slowdown=2), Path(output)/"received") as net:
        configure_showcase(net)
        net.run()
        net.export(output)
        return net.summary()
