"""Test: verifica che stems con SR diversi mantengano l'allineamento dopo _align().
Crea 3 stem con click allo stesso timestamp, li carica, e misura se i click
sono ancora allo stesso campione dopo resample + zero-pad."""

import numpy as np
import soundfile as sf
import tempfile, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from redline.input_loader import load_stems_dir


def _make_click_stem(path: str, sr: int, dur_sec: float, click_sec: float) -> None:
    """Crea un file WAV con un click (impulso) a click_sec secondi."""
    n = int(sr * dur_sec)
    data = np.zeros((n, 2), dtype=np.float32)
    click_sample = int(click_sec * sr)
    if click_sample < n:
        data[click_sample] = 1.0
    sf.write(path, data, sr)


def test_stems_with_mixed_sr_keep_alignment():
    """Tre stem con SR diversi (44.1k, 48k, 44.1k), click allo stesso timestamp.
    Dopo _align(), i click devono essere allo stesso campione nel dominio target_sr."""
    tmp = tempfile.mkdtemp()

    dur = 3.0
    click = 0.5  # click a 0.5s in tutte

    _make_click_stem(os.path.join(tmp, "lead_vocals.wav"), 44100, dur, click)
    _make_click_stem(os.path.join(tmp, "guitar.wav"), 48000, dur, click)
    _make_click_stem(os.path.join(tmp, "bass.wav"), 44100, dur, click)

    stems = load_stems_dir(tmp)

    target_sr = stems.sample_rate
    print(f"\nTarget SR: {target_sr}Hz")
    print(f"{'Stem':<25} {'SR':<8} {'Campioni':<12} {'Durata (s)':<12} {'Click @campione':<16} {'Click @tempo (s)':<16}")
    print("-" * 90)

    click_positions = {}
    for name, audio in stems.tracks.items():
        # Trova il primo sample > soglia (il click)
        mono = audio.mean(axis=1)
        threshold = 0.5
        peaks = np.where(np.abs(mono) > threshold)[0]
        click_sample = peaks[0] if len(peaks) > 0 else -1
        click_time = click_sample / target_sr if click_sample >= 0 else -1.0
        dur_s = audio.shape[0] / target_sr
        click_positions[name] = click_sample
        print(f"{name:<25} {target_sr:<8} {audio.shape[0]:<12} {dur_s:<12.3f} {click_sample:<16} {click_time:<16.3f}")

    # Verifica: tutti i click devono essere allo stesso campione (±1 sample di tolleranza)
    ref_name = list(click_positions.keys())[0]
    ref_pos = click_positions[ref_name]
    print(f"\nRiferimento: {ref_name} @ campione {ref_pos}")

    all_aligned = True
    for name, pos in click_positions.items():
        diff = abs(pos - ref_pos)
        ok = diff <= 1
        status = "✅" if ok else "❌"
        if not ok:
            all_aligned = False
        print(f"  {status} {name}: diff={diff} campioni {'(OK)' if ok else '(DRIFT!)'}")

    if all_aligned:
        print("\n✅ TUTTI ALLINEATI — nessun drift da SR misti")
    else:
        print("\n❌ DRIFT RILEVATO — stems con SR diversi perdono allineamento dopo _align()")

    # Pulisci
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    assert all_aligned, f"Stems disallineati dopo _align()! ref={ref_pos}, altri={click_positions}"


if __name__ == "__main__":
    test_stems_with_mixed_sr_keep_alignment()
