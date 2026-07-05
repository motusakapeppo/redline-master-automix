"""Closed-question CLI wizard. Deliberately simple choices (not free text/LLM)
so every answer maps directly and predictably onto a mix engine parameter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MixPreferences:
    aggressiveness: int = 3       # 1 (gentle) .. 5 (loud/pushed)
    warmth: float = 0.0           # -1 (cold/bright) .. +1 (warm/dark)
    vocal_prominence: float = 0.0 # -1 (buried) .. +1 (forward/lead)
    genre_override: str | None = None
    do_mastering: bool = True


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
        pass
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
