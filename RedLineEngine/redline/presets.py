"""Preset system for MixPreferences: save/load named configurations as JSON
files in ~/.redline/presets/, plus a set of hardcoded built-in presets that
are always available without being written to disk."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from redline.wizard import MixPreferences

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in presets — hardcoded, never written to disk
# ---------------------------------------------------------------------------
_BUILTIN_PRESETS: dict[str, dict] = {
    # ── Bilanciato (default, auto-detect tutto) ──────────────────────────
    "Bilanciato": {
        "aggressiveness": 3, "warmth": 0.0, "vocal_prominence": 0.0,
        "genre_override": None, "do_mastering": True, "platform": "auto",
        "stereo_width": 0.0, "transient_attack": 0.0, "transient_sustain": 0.0,
    },
    # ── Rock ─────────────────────────────────────────────────────────────
    "Rock - Spotify": {
        "aggressiveness": 4, "warmth": 0.0, "vocal_prominence": 0.3,
        "genre_override": "Pop / Rock", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.3, "transient_attack": 2.0, "transient_sustain": -1.0,
    },
    "Rock - Club": {
        "aggressiveness": 5, "warmth": 0.2, "vocal_prominence": 0.2,
        "genre_override": "Pop / Rock", "do_mastering": True, "platform": "club",
        "stereo_width": 0.4, "transient_attack": 3.0, "transient_sustain": -1.5,
    },
    "Rock - YouTube": {
        "aggressiveness": 4, "warmth": 0.0, "vocal_prominence": 0.3,
        "genre_override": "Pop / Rock", "do_mastering": True, "platform": "youtube",
        "stereo_width": 0.3, "transient_attack": 2.0, "transient_sustain": -1.0,
    },
    # ── Pop ───────────────────────────────────────────────────────────────
    "Pop - Spotify": {
        "aggressiveness": 3, "warmth": 0.2, "vocal_prominence": 0.5,
        "genre_override": "Pop / Rock", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.4, "transient_attack": 1.5, "transient_sustain": -0.5,
    },
    "Pop - Apple Music": {
        "aggressiveness": 3, "warmth": 0.3, "vocal_prominence": 0.4,
        "genre_override": "Pop / Rock", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.4, "transient_attack": 1.5, "transient_sustain": -0.5,
    },
    "Pop - Radio": {
        "aggressiveness": 4, "warmth": 0.3, "vocal_prominence": 0.6,
        "genre_override": "Pop / Rock", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.3, "transient_attack": 2.0, "transient_sustain": -1.0,
    },
    # ── EDM / Urban ──────────────────────────────────────────────────────
    "EDM - Club": {
        "aggressiveness": 5, "warmth": -0.3, "vocal_prominence": 0.2,
        "genre_override": "EDM / Urban", "do_mastering": True, "platform": "club",
        "stereo_width": 0.6, "transient_attack": 4.0, "transient_sustain": -2.0,
    },
    "EDM - Spotify": {
        "aggressiveness": 4, "warmth": -0.2, "vocal_prominence": 0.3,
        "genre_override": "EDM / Urban", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.5, "transient_attack": 3.0, "transient_sustain": -1.5,
    },
    "EDM - YouTube": {
        "aggressiveness": 4, "warmth": -0.2, "vocal_prominence": 0.3,
        "genre_override": "EDM / Urban", "do_mastering": True, "platform": "youtube",
        "stereo_width": 0.5, "transient_attack": 3.0, "transient_sustain": -1.5,
    },
    # ── Hip-Hop ──────────────────────────────────────────────────────────
    "Hip-Hop - Club": {
        "aggressiveness": 5, "warmth": 0.0, "vocal_prominence": 0.3,
        "genre_override": "Hip-Hop", "do_mastering": True, "platform": "club",
        "stereo_width": 0.3, "transient_attack": 4.0, "transient_sustain": -2.0,
    },
    "Hip-Hop - Spotify": {
        "aggressiveness": 4, "warmth": 0.1, "vocal_prominence": 0.4,
        "genre_override": "Hip-Hop", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.3, "transient_attack": 3.0, "transient_sustain": -1.5,
    },
    "Hip-Hop - Apple Music": {
        "aggressiveness": 4, "warmth": 0.2, "vocal_prominence": 0.4,
        "genre_override": "Hip-Hop", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.3, "transient_attack": 3.0, "transient_sustain": -1.5,
    },
    # ── Acoustic / Classical ─────────────────────────────────────────────
    "Acoustic - Apple Music": {
        "aggressiveness": 2, "warmth": 0.5, "vocal_prominence": 0.2,
        "genre_override": "Acoustic / Classical", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.2, "transient_attack": 0.0, "transient_sustain": 0.0,
    },
    "Acoustic - YouTube": {
        "aggressiveness": 2, "warmth": 0.4, "vocal_prominence": 0.2,
        "genre_override": "Acoustic / Classical", "do_mastering": True, "platform": "youtube",
        "stereo_width": 0.2, "transient_attack": 0.0, "transient_sustain": 0.0,
    },
    "Classical - Apple Music": {
        "aggressiveness": 1, "warmth": 0.3, "vocal_prominence": 0.0,
        "genre_override": "Acoustic / Classical", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.3, "transient_attack": -1.0, "transient_sustain": 0.0,
    },
    # ── Jazz / Vintage ───────────────────────────────────────────────────
    "Jazz - Apple Music": {
        "aggressiveness": 2, "warmth": 0.6, "vocal_prominence": 0.1,
        "genre_override": "Jazz / Vintage", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.3, "transient_attack": 0.0, "transient_sustain": 0.0,
    },
    "Jazz - Club": {
        "aggressiveness": 2, "warmth": 0.5, "vocal_prominence": 0.1,
        "genre_override": "Jazz / Vintage", "do_mastering": True, "platform": "club",
        "stereo_width": 0.4, "transient_attack": 0.0, "transient_sustain": 0.0,
    },
    "Vintage - Spotify": {
        "aggressiveness": 2, "warmth": 0.8, "vocal_prominence": 0.0,
        "genre_override": "Jazz / Vintage", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.2, "transient_attack": -1.0, "transient_sustain": 1.0,
    },
    # ── Stili trasversali ────────────────────────────────────────────────
    "Radio (generico)": {
        "aggressiveness": 4, "warmth": 0.3, "vocal_prominence": 0.5,
        "genre_override": None, "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.3, "transient_attack": 2.0, "transient_sustain": -1.0,
    },
    "Caldo Vintage": {
        "aggressiveness": 2, "warmth": 0.8, "vocal_prominence": -0.2,
        "genre_override": None, "do_mastering": True, "platform": "auto",
        "stereo_width": 0.2, "transient_attack": -1.0, "transient_sustain": 1.0,
    },
    "Moderno Brillante": {
        "aggressiveness": 4, "warmth": -0.5, "vocal_prominence": 0.3,
        "genre_override": None, "do_mastering": True, "platform": "auto",
        "stereo_width": 0.5, "transient_attack": 3.0, "transient_sustain": -1.5,
    },
    "Morbido Acustico": {
        "aggressiveness": 1, "warmth": 0.5, "vocal_prominence": 0.2,
        "genre_override": None, "do_mastering": True, "platform": "auto",
        "stereo_width": 0.0, "transient_attack": 0.0, "transient_sustain": 0.0,
    },
    "Loudness War": {
        "aggressiveness": 5, "warmth": -0.3, "vocal_prominence": 0.4,
        "genre_override": None, "do_mastering": True, "platform": "club",
        "stereo_width": 0.4, "transient_attack": 4.0, "transient_sustain": -3.0,
    },
    # ── Wave 1 genres (Track E3): one preset per new genre ───────────────
    "Lo-Fi": {
        "aggressiveness": 2, "warmth": 0.7, "vocal_prominence": 0.0,
        "genre_override": "Lo-Fi", "do_mastering": True, "platform": "youtube",
        "stereo_width": 0.15, "transient_attack": -1.0, "transient_sustain": 0.5,
        "mono_compatibility_target": 0.6, "bass_mono_below_hz": 120.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.5,
        "deess_amount": -0.2, "compression_amount": 0.3,
        "vocal_reverb_amount": 0.3,
    },
    "Cinematic - YouTube": {
        "aggressiveness": 2, "warmth": 0.3, "vocal_prominence": 0.1,
        "genre_override": "Cinematic", "do_mastering": True, "platform": "youtube",
        "stereo_width": 0.5, "transient_attack": -1.0, "transient_sustain": 1.0,
        "mono_compatibility_target": 0.4, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.0, "compression_amount": -0.2,
        "vocal_reverb_amount": 0.4,
    },
    "Drum & Bass - Club": {
        "aggressiveness": 5, "warmth": -0.2, "vocal_prominence": 0.1,
        "genre_override": "Drum & Bass", "do_mastering": True, "platform": "club",
        "stereo_width": 0.5, "transient_attack": 4.0, "transient_sustain": -2.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 100.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.3,
        "deess_amount": 0.0, "compression_amount": 0.4,
        "vocal_reverb_amount": 0.0,
    },
    "Reggaeton - Spotify": {
        "aggressiveness": 4, "warmth": 0.2, "vocal_prominence": 0.4,
        "genre_override": "Reggaeton", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.3, "transient_attack": 3.0, "transient_sustain": -1.5,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 110.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.2,
        "deess_amount": 0.0, "compression_amount": 0.3,
        "vocal_reverb_amount": 0.0,
    },
    "Metal - Spotify": {
        "aggressiveness": 5, "warmth": -0.1, "vocal_prominence": 0.3,
        "genre_override": "Metal", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.4, "transient_attack": 4.0, "transient_sustain": -2.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.4,
        "deess_amount": 0.2, "compression_amount": 0.5,
        "vocal_reverb_amount": 0.0,
    },
    "Country - Apple Music": {
        "aggressiveness": 3, "warmth": 0.4, "vocal_prominence": 0.5,
        "genre_override": "Country", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.3, "transient_attack": 1.5, "transient_sustain": -0.5,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.1, "compression_amount": 0.0,
        "vocal_reverb_amount": 0.2,
    },
    "Gospel - Apple Music": {
        "aggressiveness": 3, "warmth": 0.4, "vocal_prominence": 0.6,
        "genre_override": "Gospel", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.4, "transient_attack": 1.0, "transient_sustain": 0.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.0, "compression_amount": 0.2,
        "vocal_reverb_amount": 0.4,
    },
    "Funk - Spotify": {
        "aggressiveness": 4, "warmth": 0.2, "vocal_prominence": 0.3,
        "genre_override": "Funk", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.4, "transient_attack": 3.0, "transient_sustain": -1.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.3,
        "deess_amount": 0.0, "compression_amount": 0.2,
        "vocal_reverb_amount": 0.0,
    },
    "Ambient - Apple Music": {
        "aggressiveness": 1, "warmth": 0.5, "vocal_prominence": -0.2,
        "genre_override": "Ambient", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.6, "transient_attack": -2.0, "transient_sustain": 1.5,
        "mono_compatibility_target": 0.3, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.0, "compression_amount": -0.4,
        "vocal_reverb_amount": 0.5,
    },
    "Trap - Club": {
        "aggressiveness": 5, "warmth": 0.0, "vocal_prominence": 0.3,
        "genre_override": "Trap", "do_mastering": True, "platform": "club",
        "stereo_width": 0.3, "transient_attack": 4.0, "transient_sustain": -2.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 90.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.3,
        "deess_amount": 0.0, "compression_amount": 0.4,
        "vocal_reverb_amount": 0.0,
    },
    "R&B - Apple Music": {
        "aggressiveness": 3, "warmth": 0.5, "vocal_prominence": 0.5,
        "genre_override": "R&B", "do_mastering": True, "platform": "apple",
        "stereo_width": 0.35, "transient_attack": 1.0, "transient_sustain": -0.5,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.2, "compression_amount": 0.2,
        "vocal_reverb_amount": 0.3,
    },
    "Blues - Spotify": {
        "aggressiveness": 3, "warmth": 0.6, "vocal_prominence": 0.3,
        "genre_override": "Blues", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.25, "transient_attack": 1.0, "transient_sustain": 0.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.3,
        "deess_amount": 0.0, "compression_amount": 0.0,
        "vocal_reverb_amount": 0.2,
    },
    "Reggae - Spotify": {
        "aggressiveness": 3, "warmth": 0.5, "vocal_prominence": 0.3,
        "genre_override": "Reggae", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.35, "transient_attack": 2.0, "transient_sustain": -0.5,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 100.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.2,
        "deess_amount": 0.0, "compression_amount": 0.0,
        "vocal_reverb_amount": 0.3,
    },
    "Afrobeats - Spotify": {
        "aggressiveness": 4, "warmth": 0.3, "vocal_prominence": 0.4,
        "genre_override": "Afrobeats", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.4, "transient_attack": 3.0, "transient_sustain": -1.0,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 110.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.1, "compression_amount": 0.3,
        "vocal_reverb_amount": 0.0,
    },
    "K-Pop - Spotify": {
        "aggressiveness": 4, "warmth": 0.1, "vocal_prominence": 0.6,
        "genre_override": "K-Pop", "do_mastering": True, "platform": "spotify",
        "stereo_width": 0.5, "transient_attack": 3.0, "transient_sustain": -1.5,
        "mono_compatibility_target": 0.0, "bass_mono_below_hz": 0.0,
        "reference_lufs_target": 0.0, "saturation_amount": 0.0,
        "deess_amount": 0.3, "compression_amount": 0.4,
        "vocal_reverb_amount": 0.2,
    },
}


def _preset_dir() -> Path:
    """Return the user preset directory, creating it if necessary."""
    d = Path.home() / ".redline" / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _preset_path(name: str) -> Path:
    """Return the filesystem path for a user preset name."""
    return _preset_dir() / f"{name}.json"


def _is_builtin(name: str) -> bool:
    return name in _BUILTIN_PRESETS


class PresetManager:
    """Manages MixPreferences presets — built-in (hardcoded) and user-defined
    (JSON files in ~/.redline/presets/)."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def save(prefs: MixPreferences, name: str) -> None:
        """Save a MixPreferences as a named user preset (JSON).

        Raises ``ValueError`` if *name* collides with a built-in preset
        (built-ins are read-only and cannot be overwritten).
        """
        if _is_builtin(name):
            raise ValueError(f"'{name}' è un preset predefinito e non può essere sovrascritto.")

        data = {
            "aggressiveness": prefs.aggressiveness,
            "warmth": prefs.warmth,
            "vocal_prominence": prefs.vocal_prominence,
            "genre_override": prefs.genre_override,
            "do_mastering": prefs.do_mastering,
            "platform": prefs.platform,
            "stereo_width": prefs.stereo_width,
            "transient_attack": prefs.transient_attack,
            "transient_sustain": prefs.transient_sustain,
            # Wave 1 (Track E1) params — persisted since Wave 2 / Track E3.
            # Old preset files lacking these keys still load: MixPreferences
            # defaults them to 0.0 (see tests/test_presets_new.py).
            "mono_compatibility_target": prefs.mono_compatibility_target,
            "bass_mono_below_hz": prefs.bass_mono_below_hz,
            "reference_lufs_target": prefs.reference_lufs_target,
            "saturation_amount": prefs.saturation_amount,
            "deess_amount": prefs.deess_amount,
            "compression_amount": prefs.compression_amount,
            "vocal_reverb_amount": prefs.vocal_reverb_amount,
        }
        path = _preset_path(name)
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info("Preset salvato: %s -> %s", name, path)
        except OSError as exc:
            log.error("Impossibile salvare il preset '%s': %s", name, exc)
            raise

    @staticmethod
    def load(name: str) -> MixPreferences:
        """Load a preset by name — checks built-ins first, then user JSON.

        Raises ``KeyError`` if *name* does not exist anywhere.
        """
        # Built-in?
        if _is_builtin(name):
            data = _BUILTIN_PRESETS[name]
            return MixPreferences(**data)

        # User preset on disk?
        path = _preset_path(name)
        if not path.exists():
            raise KeyError(f"Preset '{name}' non trovato.")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Errore leggendo il preset '%s': %s", name, exc)
            raise KeyError(f"Impossibile caricare il preset '{name}': {exc}") from exc

        return MixPreferences(**data)

    @staticmethod
    def list() -> list[str]:
        """Return all available preset names (built-in + user), sorted."""
        builtins = list(_BUILTIN_PRESETS.keys())
        user = sorted(
            p.stem for p in _preset_dir().iterdir()
            if p.suffix == ".json" and p.stem not in _BUILTIN_PRESETS
        )
        return builtins + user

    @staticmethod
    def delete(name: str) -> None:
        """Delete a user preset by name.

        Raises ``ValueError`` if *name* is a built-in preset (built-ins
        cannot be deleted).  Raises ``KeyError`` if the user preset does
        not exist on disk.
        """
        if _is_builtin(name):
            raise ValueError(f"'{name}' è un preset predefinito e non può essere cancellato.")

        path = _preset_path(name)
        if not path.exists():
            raise KeyError(f"Preset '{name}' non trovato.")

        try:
            path.unlink()
            log.info("Preset cancellato: %s", name)
        except OSError as exc:
            log.error("Impossibile cancellare il preset '%s': %s", name, exc)
            raise

    @staticmethod
    def list_builtins() -> list[str]:
        """Return only the built-in preset names."""
        return list(_BUILTIN_PRESETS.keys())
