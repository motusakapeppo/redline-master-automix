"""Standalone entrypoint: input -> analysis -> wizard -> mix -> optional master.

Usage:
  python -m redline.cli --stems-dir PATH --out OUTDIR
  python -m redline.cli --vocals V.wav --instrumental I.wav --out OUTDIR
  python -m redline.cli --input song.wav --out OUTDIR
  (add --reference REF.wav to master-match against a reference track instead
   of fixed platform loudness targets; add --non-interactive to skip the
   wizard and use default preferences; add --platform spotify|apple|youtube|club|auto)
"""

from __future__ import annotations

import argparse
import os
import sys

import soundfile as sf

from .input_loader import load_stems_dir, load_two_track, load_single_file
from .analyze import analyze
from .wizard import run_wizard
from .mixengine import render_mix
from .masterengine import render_master, render_master_reference


def _narrate(msg: str) -> None:
    print(f"[RedLine] {msg}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RedLine Engine — standalone mix + mastering")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--stems-dir", help="Folder with an arbitrary number of named stem files")
    src.add_argument("--vocals", help="Path to a pre-mixed vocals track (pair with --instrumental)")
    src.add_argument("--input", help="Single mixed file — auto-separated via Demucs")
    p.add_argument("--instrumental", help="Path to a pre-mixed instrumental track (pairs with --vocals)")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--reference", help="Optional reference track for reference-matched mastering")
    p.add_argument("--platform", default="auto", choices=["auto", "spotify", "apple", "youtube", "club"])
    p.add_argument("--non-interactive", action="store_true", help="Skip the wizard, use default preferences")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.vocals and not args.instrumental:
        print("--vocals richiede anche --instrumental", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)

    _narrate("Carico l'audio...")
    if args.stems_dir:
        stems = load_stems_dir(args.stems_dir)
    elif args.vocals:
        stems = load_two_track(args.vocals, args.instrumental)
    else:
        _narrate("File singolo: separazione stem con Demucs (può richiedere qualche minuto)...")
        stems = load_single_file(args.input, work_dir=os.path.join(args.out, "_demucs"))
    _narrate(f"Caricati {len(stems.names())} stem: {', '.join(stems.names())} @ {stems.sample_rate}Hz")

    _narrate("Analizzo bpm, tonalità, genere, loudness e bilanciamento spettrale...")
    analysis = analyze(stems)
    _narrate(
        f"BPM {analysis.bpm:.1f}  |  Tonalità {analysis.key_name}  |  Genere {analysis.genre.name}  |  "
        f"{analysis.mix_lufs:.1f} LUFS  |  Crest {analysis.mix_crest:.1f}"
    )

    prefs = run_wizard(analysis.genre.name, interactive=not args.non_interactive)

    _narrate("Avvio il mix...")
    mixed = render_mix(stems, analysis, prefs, on_step=_narrate)

    mix_path = os.path.join(args.out, "mix.wav")
    sf.write(mix_path, mixed, stems.sample_rate)
    _narrate(f"Mix salvato: {mix_path}")

    if prefs.do_mastering:
        _narrate("Avvio il mastering...")
        if args.reference:
            master_path = os.path.join(args.out, "master.wav")
            render_master_reference(mix_path, args.reference, master_path, on_step=_narrate)
        else:
            mastered = render_master(mixed, stems.sample_rate, analysis, platform=args.platform, on_step=_narrate)
            master_path = os.path.join(args.out, "master.wav")
            sf.write(master_path, mastered, stems.sample_rate)
        _narrate(f"Master salvato: {master_path}")

    _narrate("Fatto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
