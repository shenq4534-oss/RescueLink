"""Self describing fixed robust header, no out-of-band payload parameters."""
import struct
import zlib
import numpy as np
from rescuelink.config import SAMPLE_RATE
from .bits import to_bits, from_bits
from . import coding
from .modulation import modulate, demodulate

PREAMBLE = np.tile(np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=np.uint8), 4)
PHY = struct.Struct("!BBBBH")  # version, scheme, fec, spb/8, byte length
SCHEMES = {"BPSK": 1, "ASK": 2, "BFSK": 3}
HEADER_SPB = 64
HEADER_BITS = (PHY.size + 4) * 8 * 3
PREFIX_SAMPLES = (len(PREAMBLE) + HEADER_BITS) * HEADER_SPB

def encode(raw, mode, scheme="BPSK"):
    if not 1 <= len(raw) <= 1024:
        raise ValueError("PHY length")
    h = PHY.pack(1, SCHEMES[scheme], int(mode.fec), mode.spb // 8, len(raw))
    h += struct.pack("!I", zlib.crc32(h))
    bits = to_bits(raw)
    coded = coding.encode(bits) if mode.fec else bits
    prefix = modulate(np.concatenate([PREAMBLE, np.repeat(to_bits(h), 3)]), spb=HEADER_SPB)
    return np.concatenate([prefix, modulate(coded, scheme, mode.spb)]), coded

def decode(signal):
    if len(signal) < PREFIX_SAMPLES:
        raise ValueError("short PHY")
    p = demodulate(signal[:PREFIX_SAMPLES], spb=HEADER_SPB)
    if np.count_nonzero(p[:len(PREAMBLE)] != PREAMBLE) > 3:
        raise ValueError("preamble")
    hb = (p[len(PREAMBLE):].reshape(-1, 3).sum(axis=1) >= 2).astype(np.uint8)
    h = from_bits(hb)
    if zlib.crc32(h[:-4]) != struct.unpack("!I", h[-4:])[0]:
        raise ValueError("PHY header CRC")
    v, sid, fec, unit, size = PHY.unpack(h[:-4])
    if v != 1 or sid not in SCHEMES.values() or fec not in (0, 1) or unit not in (1, 2, 8) or not 1 <= size <= 1024:
        raise ValueError("PHY parameters")
    spb = unit * 8
    nbits = size * 8 * (2 if fec else 1)
    if len(signal) != PREFIX_SAMPLES + nbits * spb:
        raise ValueError("PHY payload length")
    # Least-squares gain and residual noise estimated only from known training.
    train = modulate(PREAMBLE, spb=HEADER_SPB)
    observed = signal[:len(train)]
    gain = max(1e-6, float(observed @ train / (train @ train)))
    noise_power = float(np.mean((observed - gain * train) ** 2))
    signal_power = float(np.mean((gain * train) ** 2))
    snr = signal_power / max(noise_power, 1e-15)
    scheme = next(k for k, val in SCHEMES.items() if val == sid)
    raw_bits = demodulate(signal[PREFIX_SAMPLES:], scheme, spb, gain)
    bits, stats = coding.decode(raw_bits) if fec else (raw_bits, coding.DecodeStats())
    return from_bits(bits), stats, raw_bits, snr
