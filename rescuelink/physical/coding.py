"""Handwritten extended Hamming (8,4), positions 1,2,4 parity, 8 overall."""
from dataclasses import dataclass
import numpy as np

@dataclass
class DecodeStats:
    corrected_codewords: int = 0
    detected_uncorrectable: int = 0

def encode(bits):
    b = np.asarray(bits, dtype=np.uint8)
    if b.ndim != 1 or len(b) % 4 or np.any(b > 1):
        raise ValueError("Hamming input must be binary, multiple of four")
    d = b.reshape(-1, 4)
    c = np.zeros((len(d), 8), dtype=np.uint8)
    c[:, [2, 4, 5, 6]] = d
    c[:, 0] = c[:, 2] ^ c[:, 4] ^ c[:, 6]
    c[:, 1] = c[:, 2] ^ c[:, 5] ^ c[:, 6]
    c[:, 3] = c[:, 4] ^ c[:, 5] ^ c[:, 6]
    c[:, 7] = np.bitwise_xor.reduce(c[:, :7], axis=1)
    return c.ravel()

def decode(bits):
    b = np.asarray(bits, dtype=np.uint8)
    if b.ndim != 1 or len(b) % 8 or np.any(b > 1):
        raise ValueError("invalid codeword")
    c = b.reshape(-1, 8).copy()
    s = ((c[:, 0] ^ c[:, 2] ^ c[:, 4] ^ c[:, 6]) +
         2 * (c[:, 1] ^ c[:, 2] ^ c[:, 5] ^ c[:, 6]) +
         4 * (c[:, 3] ^ c[:, 4] ^ c[:, 5] ^ c[:, 6]))
    odd = np.bitwise_xor.reduce(c, axis=1).astype(bool)
    rows = np.flatnonzero(odd)
    positions = np.where(s[rows] == 0, 7, s[rows] - 1)
    c[rows, positions] ^= 1
    stats = DecodeStats(len(rows), int(np.count_nonzero((s != 0) & ~odd)))
    return c[:, [2, 4, 5, 6]].ravel(), stats
