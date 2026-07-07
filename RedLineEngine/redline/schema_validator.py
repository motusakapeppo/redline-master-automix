"""Validates preset/config JSON against a schema before it reaches the
pipeline, so a missing field or an out-of-range value falls back to a
sensible default instead of crashing mid-processing with a bare
KeyError/TypeError."""

from __future__ import annotations

from dataclasses import dataclass, field

from redline.logging_setup import get_logger

logger = get_logger(__name__)

PRESET_SCHEMA = {
    "aggressiveness": {"type": "int", "min": 1, "max": 5, "default": 3},
    "warmth": {"type": "float", "min": -1.0, "max": 1.0, "default": 0.0},
    "vocal_prominence": {"type": "float", "min": -1.0, "max": 1.0, "default": 0.0},
    "genre_override": {"type": "str_or_null", "default": None},
    "do_mastering": {"type": "bool", "default": True},
    "platform": {
        "type": "str",
        "choices": ["auto", "spotify", "apple", "youtube", "club"],
        "default": "auto",
    },
    "stereo_width": {"type": "float", "min": -1.0, "max": 1.0, "default": 0.0},
    "transient_attack": {"type": "float", "min": -10.0, "max": 10.0, "default": 0.0},
    "transient_sustain": {"type": "float", "min": -10.0, "max": 10.0, "default": 0.0},
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list = field(default_factory=list)
    fixed: dict = field(default_factory=dict)


def _type_ok(value, expected: str) -> bool:
    if expected == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "str":
        return isinstance(value, str)
    if expected == "str_or_null":
        return value is None or isinstance(value, str)
    return True


class SchemaValidator:
    @staticmethod
    def validate_preset(data: dict, schema: dict) -> ValidationResult:
        errors: list[str] = []
        fixed: dict = {}

        for field_name, spec in schema.items():
            expected_type = spec["type"]
            default = spec.get("default")

            if field_name not in data:
                fixed[field_name] = default
                continue

            value = data[field_name]

            if not _type_ok(value, expected_type):
                errors.append(
                    f"{field_name}: tipo atteso {expected_type}, trovato {type(value).__name__}"
                )
                continue

            if "choices" in spec and value not in spec["choices"]:
                errors.append(f"{field_name}: valore '{value}' non tra le scelte valide {spec['choices']}")
                continue

            if expected_type in ("int", "float"):
                lo, hi = spec.get("min"), spec.get("max")
                if lo is not None and value < lo:
                    logger.warning("%s: %s sotto il minimo %s, clamped", field_name, value, lo)
                    value = lo
                if hi is not None and value > hi:
                    logger.warning("%s: %s sopra il massimo %s, clamped", field_name, value, hi)
                    value = hi

            fixed[field_name] = value

        for field_name in data:
            if field_name not in schema:
                logger.warning("%s: campo sconosciuto, ignorato", field_name)

        return ValidationResult(valid=(len(errors) == 0), errors=errors, fixed=fixed)

    @staticmethod
    def apply_defaults(data: dict, schema: dict) -> dict:
        merged = dict(data)
        for field_name, spec in schema.items():
            if field_name not in merged:
                merged[field_name] = spec.get("default")
        return merged
