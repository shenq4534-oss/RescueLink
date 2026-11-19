"""Coherent, symbol-aligned carriers; 6/12 kHz at 48 kHz sample rate."""
import numpy as np

def carriers(spb):
    if not isinstance(spb, int) or spb < 8 or spb % 8:
        raise ValueError("spb must be a positive multiple of eight >= 8")
    t = np.arange(spb)
    return np.cos(2 * np.pi * t / 8), np.cos(2 * np.pi * t / 4)

def modulate(bits, scheme="BPSK", spb=8):
    b = np.asarray(bits, dtype=np.uint8)
    if b.ndim != 1 or np.any(b > 1):
        raise ValueError("nonbinary input")
    c0, c1 = carriers(spb)
    if scheme == "BPSK":
        s = (2 * b.astype(float) - 1)[:, None] * c0
    elif scheme == "ASK":
        # OOK sqrt(2) amplitude: same *average* energy for balanced bits.
        s = np.sqrt(2) * b[:, None] * c0
    elif scheme == "BFSK":
        s = np.where(b[:, None] == 1, c1, c0)
    else:
        raise ValueError("unknown modulation")
    return s.ravel()

def demodulate(signal, scheme="BPSK", spb=8, gain=1.0):
    c0, c1 = carriers(spb)
    x = np.asarray(signal).reshape(-1, spb)
    z0 = x @ c0 / (spb / 2)
    if scheme == "BPSK":
        b = z0 > 0
    elif scheme == "ASK":
        b = z0 > gain / np.sqrt(2)
    elif scheme == "BFSK":
        b = x @ c1 > x @ c0
    else:
        raise ValueError("unknown modulation")
    return b.astype(np.uint8)
