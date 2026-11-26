from concurrent.futures import ThreadPoolExecutor
from collections import deque
from threading import Lock
from pathlib import Path
import hashlib
import inspect
import numpy as np
from cable import Cable
from rescuelink.config import SAMPLE_RATE
from .framing_phy import encode, decode, PREFIX_SAMPLES
from .bits import to_bits
from rescuelink.protocol.frame import Frame, HEADER

_RNG_LOCK = Lock()

def sample_hash(samples):
    """Canonical float64 little-endian representation, for trace correlation."""
    return hashlib.sha256(np.asarray(samples, dtype="<f8").tobytes()).hexdigest()

class PhysicalLink:
    """Own original Cable, RNG state and worker for this directed port."""
    def __init__(self, config, seed, name, capture=False):
        self.name = name
        self.cable = Cable(config.length, config.attenuation, config.noise)
        self.rng = np.random.RandomState(seed)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cable-" + name)
        self.calls = 0
        self.last = None
        self.traces = deque(maxlen=16)
        self.capture = capture
        self.source_hash = hashlib.sha256(Path(inspect.getfile(Cable)).read_bytes()).hexdigest() if capture else None

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
        trace = None
        if self.capture:
            # Observations are taken at the actual Cable call, never used to decode.
            body_start = PREFIX_SAMPLES + HEADER.size*8*(2 if mode.fec else 1)*mode.spb
            trace = dict(lane=self.name, cable_call=self.calls, cable_class="cable.Cable",
                cable_source_sha256=self.source_hash, sample_format="float64 little-endian",
                noise=self.cable.noise_level, frame_hex_tx=raw.hex(),
                frame_sha256_tx=hashlib.sha256(raw).hexdigest(), frame_sha256_rx=None,
                frame_bits_tx="".join(map(str, to_bits(raw).tolist())),
                coded_bits_tx="".join(map(str, coded.tolist())),
                coded_bits_rx=None, decoder_candidate_hex=None, payload_hex_rx=None,
                waveform_sha256_tx=sample_hash(waveform), waveform_sha256_rx=sample_hash(received),
                cable_input_matches=bool(np.array_equal(waveform, self.cable.last_input_signal)),
                cable_output_matches=bool(np.array_equal(received, self.cable.last_output_signal)),
                samples=len(waveform), payload_offset_samples=PREFIX_SAMPLES,
                body_offset_samples=body_start,
                body_coded_bit_offset=HEADER.size*8*(2 if mode.fec else 1),
                payload_tx=waveform[PREFIX_SAMPLES:PREFIX_SAMPLES+24*mode.spb].tolist(),
                payload_rx=received[PREFIX_SAMPLES:PREFIX_SAMPLES+24*mode.spb].tolist(),
                body_tx=waveform[body_start:body_start+24*mode.spb].tolist(),
                body_rx=received[body_start:body_start+24*mode.spb].tolist())
        result = dict(ok=False, error="", corrected_codewords=0, detected_uncorrectable=0,
                      trace_id=self.calls, raw_errors=0, coded_bits=len(coded), information_bits=len(raw)*8,
                      samples=len(waveform), snr_linear=None, raw=None, post_errors=None,
                      duration=len(waveform)/SAMPLE_RATE*slowdown,
                      propagation=self.cable.get_propagation_delay(),
                      tx=waveform[:512].tolist(), rx=received[:512].tolist(),
                      tx_payload=waveform[PREFIX_SAMPLES:PREFIX_SAMPLES+512].tolist(),
                      rx_payload=received[PREFIX_SAMPLES:PREFIX_SAMPLES+512].tolist())
        try:
            decoded, stats, raw_rx, snr = decode(received, trace)
            result.update(corrected_codewords=stats.corrected_codewords,
                          detected_uncorrectable=stats.detected_uncorrectable,
                          raw_errors=int(np.count_nonzero(coded != raw_rx)), snr_linear=snr,
                          post_errors=int(np.count_nonzero(to_bits(raw) != to_bits(decoded))))
            if stats.detected_uncorrectable:
                raise ValueError("FEC uncorrectable")
            frame = Frame.unpack(decoded)
            result.update(ok=True, raw=decoded)
            if trace is not None:
                trace.update(payload_hex_rx=frame.payload.hex(),
                             frame_sha256_rx=hashlib.sha256(decoded).hexdigest())
        except ValueError as exc:
            result["error"] = str(exc)
        if trace is not None:
            trace.update(ok=result["ok"], error=result["error"], mode=mode.name, modulation=scheme,
                         corrected_codewords=result["corrected_codewords"],
                         detected_uncorrectable=result["detected_uncorrectable"])
            result["trace"] = trace
            self.traces.append(dict(trace, trace_id=self.calls,
                tx_payload=result["tx_payload"], rx_payload=result["rx_payload"],
                raw=result["raw"]))
        self.last = result
        return result

    def close(self):
        self.worker.shutdown(wait=True, cancel_futures=True)
