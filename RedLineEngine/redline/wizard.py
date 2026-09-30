"""Closed-question CLI wizard. Deliberately simple choices (not free text/LLM)
so every answer maps directly and predictably onto a mix engine parameter."""

from __future__ import annotations

from dataclasses import dataclass

from redline.logging_setup import get_logger
from redline.platforms import PLATFORM_CHOICES

logger = get_logger(__name__)


@dataclass
class MixPreferences:
    aggressiveness: int = 3       # 1 (gentle) .. 5 (loud/pushed)
    warmth: float = 0.0           # -1 (cold/bright) .. +1 (warm/dark)
    vocal_prominence: float = 0.0 # -1 (buried) .. +1 (forward/lead)
    genre_override: str | None = None
    do_mastering: bool = True
    platform: str = "auto"       # "auto" | "spotify" | "apple" | "youtube" | "club"
    stereo_width: float = 0.0    # 0=off, 0.1-1.0 range
    transient_attack: float = 0.0 # 0=off, -6..+6 range
    transient_sustain: float = 0.0 # 0=off, -6..+6 range
    # --- Wave 1 (Track E1) user-exposed parameters -------------------------
    # All default to 0.0 = engine default, no change. They are optional
    # overrides consumed by the engine in Wave 2; the interactive wizard
    # does not ask for them.
    mono_compatibility_target: float = 0.0  # 0.0 = auto/genre default; 0.0..1.0 QC mono target
    bass_mono_below_hz: float = 0.0         # 0.0 = engine default (120 Hz); 0.0..300.0
    reference_lufs_target: float = 0.0      # 0.0 = use platform/genre target; -30.0..0.0
    saturation_amount: float = 0.0          # 0.0 = engine default, no change; -1..+1 scales per-instrument/drum saturation
    deess_amount: float = 0.0               # 0.0 = engine default, no change; -1..+1 scales de-esser intensity
    compression_amount: float = 0.0         # 0.0 = engine default, no change; -1..+1 global bias on per-stem compressor ratios
    vocal_reverb_amount: float = 0.0        # 0.0 = engine default, no change; -1..+1 bias on the vocal space send

    def __post_init__(self) -> None:
        # Defense in depth: the GUI's range inputs already constrain these
        # (and the free-text creative-brief path is separately clamped by
        # director_safety.clamp_params before it ever reaches here), but
        # MixPreferences itself is a plain constructible dataclass -- any
        # future caller (a script, a different frontend, a bug) could hand
        # it an out-of-range value, and the mix engine trusts these at face
        # value in gain-scaling formulas (e.g. vocal_gain_db). Clamping here
        # guarantees no combination of inputs can push those formulas into
        # destructive territory, no matter how it got constructed.
        self.aggressiveness = int(max(1, min(5, self.aggressiveness)))
        self.warmth = float(max(-1.0, min(1.0, self.warmth)))
        self.vocal_prominence = float(max(-1.0, min(1.0, self.vocal_prominence)))
        self.stereo_width = float(max(0.0, min(1.0, self.stereo_width)))
        self.transient_attack = float(max(-6.0, min(6.0, self.transient_attack)))
        self.transient_sustain = float(max(-6.0, min(6.0, self.transient_sustain)))
        self.mono_compatibility_target = float(max(0.0, min(1.0, self.mono_compatibility_target)))
        self.bass_mono_below_hz = float(max(0.0, min(300.0, self.bass_mono_below_hz)))
        self.reference_lufs_target = float(max(-30.0, min(0.0, self.reference_lufs_target)))
        self.saturation_amount = float(max(-1.0, min(1.0, self.saturation_amount)))
        self.deess_amount = float(max(-1.0, min(1.0, self.deess_amount)))
        self.compression_amount = float(max(-1.0, min(1.0, self.compression_amount)))
        self.vocal_reverb_amount = float(max(-1.0, min(1.0, self.vocal_reverb_amount)))
        if self.platform not in PLATFORM_CHOICES:
            self.platform = "auto"


def _ask_choice(prompt: str, options: dict[str, tuple[str, float]], default_key: str) -> float:
    """Prints numbered options, returns the numeric value tied to the chosen key."""
    print(f"\n{prompt}")
    keys = list(options.keys())
    for i, key in enumerate(keys, 1):
        label, _ = options[key]
        marker = " (default)" if key == default_key else ""
        print(f"  {i}. {label}{marker}")

    raw = input(f"Scelta [1-{len(keys)}, invio per default]: ").strip()
    if not raw:
        return options[default_key][1]
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            return options[keys[idx]][1]
    except ValueError:
        logger.warning("Invalid menu choice — using default")
    print("Scelta non valida, uso il default.")
    return options[default_key][1]


def run_wizard(detected_genre: str, interactive: bool = True) -> MixPreferences:
    if not interactive:
        return MixPreferences()

    print("=" * 60)
    print(f"Genere rilevato: {detected_genre}")
    print("Rispondi a qualche domanda per guidare il mix (invio = default).")
    print("=" * 60)

    aggressiveness = int(
        _ask_choice(
            "Quanto deve essere spinto/aggressivo il mix?",
            {
                "gentle": ("Delicato, molto dinamico", 1),
                "soft": ("Morbido", 2),
                "balanced": ("Bilanciato", 3),
                "pushed": ("Spinto", 4),
                "loud": ("Molto aggressivo/loud", 5),
            },
            default_key="balanced",
        )
    )

    warmth = _ask_choice(
        "Che carattere tonale vuoi?",
        {
            "cold": ("Freddo/brillante", -1.0),
            "neutral": ("Neutro", 0.0),
            "warm": ("Caldo/morbido sugli alti", 1.0),
        },
        default_key="neutral",
    )

    vocal_prominence = _ask_choice(
        "Come vuoi la voce nel mix?",
        {
            "back": ("Più indietro, fusa nel mix", -1.0),
            "balanced": ("Bilanciata", 0.0),
            "forward": ("In primo piano, protagonista", 1.0),
        },
        default_key="balanced",
    )

    genre_raw = input(
        "\nGenere di riferimento (invio per tenere quello rilevato): "
    ).strip()
    genre_override = genre_raw or None

    master_raw = input("\nEseguire anche il mastering dopo il mix? [S/n]: ").strip().lower()
    do_mastering = master_raw not in ("n", "no")

    return MixPreferences(
        aggressiveness=aggressiveness,
        warmth=warmth,
        vocal_prominence=vocal_prominence,
        genre_override=genre_override,
        do_mastering=do_mastering,
    )
