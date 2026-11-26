from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import numpy as np
from cable import Cable
from rescuelink.config import SAMPLE_RATE
from .framing_phy import encode, decode, PREFIX_SAMPLES
from .bits import to_bits
from rescuelink.protocol.frame import Frame

_RNG_LOCK = Lock()

class PhysicalLink:
    """Own original Cable, RNG state and worker for this directed port."""
    def __init__(self, config, seed, name):
        self.name = name
        self.cable = Cable(config.length, config.attenuation, config.noise)
        self.rng = np.random.RandomState(seed)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cable-" + name)
        self.calls = 0
        self.last = None

    def transmit(self, raw, mode, scheme="BPSK", slowdown=1):
        return self.worker.submit(self._transmit, raw, mode, scheme, slowdown).result()

    def _transmit(self, raw, mode, scheme, slowdown):
        waveform, coded = encode(raw, mode, scheme)
        # Original Cable uses global numpy RNG. Isolate without changing its file/model.
        with _RNG_LOCK:
            state = np.random.get_state()
            np.random.set_state(self.rng.get_state())
            try:
                received = self.cable.transmit(waveform)
                self.rng.set_state(np.random.get_state())
            finally:
                np.random.set_state(state)
        self.calls += 1
        result = dict(ok=False, error="", corrected_codewords=0, detected_uncorrectable=0,
                      raw_errors=0, coded_bits=len(coded), information_bits=len(raw)*8,
                      samples=len(waveform), snr_linear=None, raw=None, post_errors=None,
                      duration=len(waveform)/SAMPLE_RATE*slowdown,
                      propagation=self.cable.get_propagation_delay(),
                      tx=waveform[:512].tolist(), rx=received[:512].tolist(),
                      tx_payload=waveform[PREFIX_SAMPLES:PREFIX_SAMPLES+512].tolist(),
                      rx_payload=received[PREFIX_SAMPLES:PREFIX_SAMPLES+512].tolist())
        try:
            decoded, stats, raw_rx, snr = decode(received)
            result.update(corrected_codewords=stats.corrected_codewords,
                          detected_uncorrectable=stats.detected_uncorrectable,
                          raw_errors=int(np.count_nonzero(coded != raw_rx)), snr_linear=snr,
                          post_errors=int(np.count_nonzero(to_bits(raw) != to_bits(decoded))))
            if stats.detected_uncorrectable:
                raise ValueError("FEC uncorrectable")
            Frame.unpack(decoded)
            result.update(ok=True, raw=decoded)
        except ValueError as exc:
            result["error"] = str(exc)
        self.last = result
        return result

    def close(self):
        self.worker.shutdown(wait=True, cancel_futures=True)
