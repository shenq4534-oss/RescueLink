import numpy as np

def to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))

def from_bits(bits) -> bytes:
    a = np.asarray(bits, dtype=np.uint8)
    if a.ndim != 1 or len(a) % 8 or np.any(a > 1):
        raise ValueError("bits must be binary and byte aligned")
    return np.packbits(a).tobytes()
