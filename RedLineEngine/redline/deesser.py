"""Band-split de-esser for vocal stems: reduces sibilance without touching
the rest of the signal. Adaptive by default — sibilance isn't always
5-9kHz, it shifts with the singer/mic, so this measures where THIS stem's
high-frequency energy actually peaks (during its loudest high-band moments,
i.e. actual "S"/"T" consonants) and centers the cut band there, instead of
using one fixed band for every voice."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

from .dsp_utils import envelope_follower

SIBILANCE_SEARCH_LOW_HZ = 3000.0
SIBILANCE_SEARCH_HIGH_HZ = 11000.0
DEFAULT_BAND_HALF_WIDTH_HZ = 1500.0
FALLBACK_CENTER_HZ = 7000.0  # used when detection can't find a clear peak


@dataclass
class SibilanceBand:
    low_hz: float
    high_hz: float


def detect_sibilance_band(signal: np.ndarray, sr: int, half_width_hz: float = DEFAULT_BAND_HALF_WIDTH_HZ) -> SibilanceBand:
    """Finds the frequency where high-band energy concentrates during the
    loudest high-frequency moments of the stem (consonant transients), via a
    Welch PSD restricted to the search range."""
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    mono = mono.astype(np.float64)
    nyquist = sr / 2.0
    high = min(SIBILANCE_SEARCH_HIGH_HZ, nyquist * 0.99)

    if mono.size < sr // 4 or high <= SIBILANCE_SEARCH_LOW_HZ:
        return SibilanceBand(FALLBACK_CENTER_HZ - half_width_hz, FALLBACK_CENTER_HZ + half_width_hz)

    # Isolate the search band, then look only at its loudest quarter (by
    # short-time energy) so the peak reflects consonant transients rather
    # than being averaged out by long stretches of vowel/silence.
    sos = butter(4, [SIBILANCE_SEARCH_LOW_HZ / nyquist, high / nyquist], btype="bandpass", output="sos")
    band_signal = sosfiltfilt(sos, mono)

    block = max(1, sr // 20)  # 50ms blocks
    n_blocks = band_signal.size // block
    if n_blocks < 4:
        segment = band_signal
    else:
        blocks = band_signal[: n_blocks * block].reshape(n_blocks, block)
        block_energy = np.mean(blocks**2, axis=1)
        loudest = np.argsort(block_energy)[-max(1, n_blocks // 4):]
        segment = blocks[loudest].reshape(-1)

    if segment.size < 256:
        return SibilanceBand(FALLBACK_CENTER_HZ - half_width_hz, FALLBACK_CENTER_HZ + half_width_hz)

    freqs, psd = welch(segment, fs=sr, nperseg=min(2048, segment.size))
    mask = (freqs >= SIBILANCE_SEARCH_LOW_HZ) & (freqs <= high)
    if not np.any(mask):
        return SibilanceBand(FALLBACK_CENTER_HZ - half_width_hz, FALLBACK_CENTER_HZ + half_width_hz)

    peak_freq = float(freqs[mask][np.argmax(psd[mask])])
    return SibilanceBand(max(1000.0, peak_freq - half_width_hz), min(nyquist * 0.99, peak_freq + half_width_hz))


def _deess_channel(
    channel: np.ndarray,
    sr: int,
    band: SibilanceBand,
    threshold_db: float,
    max_reduction_db: float,
    attack_ms: float,
    release_ms: float,
) -> np.ndarray:
    nyquist = sr / 2.0
    sos = butter(
        4,
        [band.low_hz / nyquist, min(band.high_hz / nyquist, 0.999)],
        btype="bandpass",
        output="sos",
    )
    sibilant = sosfiltfilt(sos, channel.astype(np.float64)).astype(np.float32)
    rest = channel - sibilant  # everything outside the sibilance band, untouched

    env = envelope_follower(np.abs(sibilant), sr, attack_ms, release_ms)
    threshold_lin = max(10.0 ** (threshold_db / 20.0), 1e-9)
    excess_db = 20.0 * np.log10(np.maximum(env, 1e-9) / threshold_lin)
    reduction_db = np.clip(excess_db, 0.0, max_reduction_db)
    gain = (10.0 ** (-reduction_db / 20.0)).astype(np.float32)

    return rest + sibilant * gain


def deess(
    signal: np.ndarray,
    sr: int,
    threshold_db: float = -30.0,
    max_reduction_db: float = 9.0,
    attack_ms: float = 2.0,
    release_ms: float = 60.0,
    band: SibilanceBand | None = None,
) -> np.ndarray:
    """If `band` isn't given, it's detected adaptively from the signal itself
    (see detect_sibilance_band) rather than assuming a fixed 5-9kHz range."""
    if band is None:
        band = detect_sibilance_band(signal, sr)

    if signal.ndim == 1:
        return _deess_channel(signal, sr, band, threshold_db, max_reduction_db, attack_ms, release_ms)
    return np.stack(
        [
            _deess_channel(signal[:, ch], sr, band, threshold_db, max_reduction_db, attack_ms, release_ms)
            for ch in range(signal.shape[1])
        ],
        axis=1,
    )
