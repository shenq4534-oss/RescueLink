import hashlib
from pathlib import Path
import numpy as np
import pytest
from rescuelink.physical.bits import to_bits, from_bits
from rescuelink.physical import coding
from rescuelink.config import Config, MODES
from rescuelink.physical.channel import PhysicalLink
from rescuelink.protocol.frame import Frame, Kind
from rescuelink.protocol.fragmentation import Reassembler
from rescuelink.simulation.scenarios import level1

@pytest.mark.unit
@pytest.mark.parametrize("data", [b"", b"hello", "中文🆘".encode(), bytes(range(256))])
def test_bits(data):
    assert from_bits(to_bits(data)) == data

@pytest.mark.unit
def test_secded_exhaustive():
    for nibble in range(16):
        bits = np.array([(nibble>>i)&1 for i in (3,2,1,0)], dtype=np.uint8)
        encoded = coding.encode(bits)
        for i in range(8):
            single = encoded.copy(); single[i] ^= 1
            out, stats = coding.decode(single)
            assert np.array_equal(out, bits) and stats.corrected_codewords == 1
            for j in range(i+1,8):
                double = single.copy(); double[j] ^= 1
                _, stats = coding.decode(double)
                assert stats.detected_uncorrectable == 1

@pytest.mark.unit
def test_crc_header_and_payload():
    raw = Frame(Kind.DATA,1,4,2,1,payload=b"abc").pack()
    for i in range(len(raw)*8):
        changed = bytearray(raw); changed[i//8] ^= 1 << (i%8)
        with pytest.raises(ValueError): Frame.unpack(changed)
    for value in (raw[:-1], b"", raw+b"0"):
        with pytest.raises(ValueError): Frame.unpack(value)

@pytest.mark.unit
def test_reassembly_out_of_order_duplicate_missing():
    r = Reassembler(3)
    assert r.add(2,3,b"c") is None
    assert r.add(2,3,b"c") is None
    assert r.add(0,3,b"a") is None
    assert r.add(1,3,b"b") == b"abc"
    with pytest.raises(ValueError): r.add(2,3,b"x")
    with pytest.raises(ValueError): r.add(1,4,b"b")

@pytest.mark.physical_channel
@pytest.mark.parametrize("scheme", ["BPSK","ASK","BFSK"])
@pytest.mark.parametrize("mode", list(MODES))
def test_original_cable_all_modulations_and_modes(scheme,mode):
    link=PhysicalLink(Config(noise=0),42,"test")
    try:
        raw=Frame(Kind.DATA,1,4,2,1,payload=bytes(range(128))).pack()
        r=link.transmit(raw, MODES[mode],scheme)
        assert r["ok"] and r["raw"] == raw
        assert r["raw_errors"] == 0 and link.calls == 1
        assert r["propagation"] == 100/2e8
    finally: link.close()

@pytest.mark.physical_channel
@pytest.mark.parametrize("data", [b"",b"hello","长中文消息".encode()*120, bytes(range(256))*2])
def test_level1_noise_fragmentation(data):
    r=level1(data,noise=.25)
    assert r["success"] and bytes.fromhex(r["received_hex"]) == data
    if len(data)>128: assert r["fragments"]>1

@pytest.mark.unit
def test_bounds():
    for kw in [dict(window=0),dict(payload=257),dict(noise=-1),dict(policy="magic")]:
        with pytest.raises(ValueError): Config(**kw)
    with pytest.raises(ValueError): from_bits([1,0])
    with pytest.raises(ValueError): Frame(Kind.DATA,0,4,0,1).pack()
