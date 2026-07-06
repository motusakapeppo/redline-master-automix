import numpy as np

from redline.reverbbus import ReverbBusSystem, ROOM, PLATE, HALL


def _tone(sr, seconds=2.0, freq=220.0, amp=0.3):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_only_three_reverb_instances_regardless_of_stem_count():
    sr = 22050
    bus = ReverbBusSystem(sr)
    assert len(bus._reverbs) == 3  # exactly Room/Plate/Hall, never grows

    # Sending many stems must not create any new Reverb instances.
    signal = _tone(sr)
    for _ in range(20):
        bus.send(signal, ROOM, 0.1)
    assert len(bus._reverbs) == 3


def test_render_combines_all_sent_buses():
    sr = 22050
    bus = ReverbBusSystem(sr)
    signal = _tone(sr)
    bus.send(signal, ROOM, 0.2)
    bus.send(signal, PLATE, 0.2)
    bus.send(signal, HALL, 0.2)

    out = bus.render()
    assert out is not None
    assert out.shape == signal.shape
    assert np.max(np.abs(out)) > 0.0


def test_render_returns_none_when_nothing_sent():
    sr = 22050
    bus = ReverbBusSystem(sr)
    assert bus.render() is None


def test_room_bus_return_has_no_sub_bass_energy():
    # The Abbey Road high-pass on the return (600Hz) must remove sub-bass
    # content. Uses broadband noise (a real drum/instrumental submix has
    # broadband content) rather than a pure low tone — a pure sine's reverb
    # tail stays monochromatic no matter how it's filtered, so it can't
    # actually demonstrate a highpass doing its job.
    sr = 22050
    n = int(sr * 2.0)
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(n).astype(np.float32) * 0.3
    broadband = np.stack([noise, noise], axis=1)

    bus = ReverbBusSystem(sr)
    bus.send(broadband, ROOM, 1.0)
    out = bus.render()

    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, 150 / (sr / 2), btype="lowpass", output="sos")
    low_energy = np.sum(sosfiltfilt(sos, out[:, 0].astype(np.float64)) ** 2)
    total_energy = np.sum(out[:, 0].astype(np.float64) ** 2) + 1e-9
    assert low_energy / total_energy < 0.05
