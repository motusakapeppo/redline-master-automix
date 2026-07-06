"""Standalone entrypoint: input -> analysis -> wizard -> mix -> optional master.

Usage:
  python -m redline.cli --folder PATH --out OUTDIR
      Point at one file or one folder and it figures out the rest: a
      folder with a pre-mixed instrumental + a "vocals stems" subfolder
      full of takes, a folder of arbitrary stems, or a single file (auto
      Demucs separation) all work without picking a mode by hand.

  Explicit modes remain available for cases that don't share one parent folder:
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

from .input_loader import load_stems_dir, load_two_track, load_single_file, load_auto
from .analyze import analyze
from .wizard import run_wizard
from .mixengine import render_mix
from .masterengine import render_master, render_master_reference
from .metrics import Metrics


def _narrate(msg: str) -> None:
    print(f"[RedLine] {msg}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RedLine Engine — standalone mix + mastering")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder", help="A single file or folder — the right loading mode is auto-detected")
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
    metrics = Metrics()

    _narrate("Carico l'audio...")
    with metrics.stage("input_loading", on_step=_narrate):
        if args.folder:
            stems = load_auto(args.folder, work_dir=os.path.join(args.out, "_demucs"), on_step=_narrate)
        elif args.stems_dir:
            stems = load_stems_dir(args.stems_dir)
        elif args.vocals:
            stems = load_two_track(args.vocals, args.instrumental)
        else:
            _narrate("File singolo: separazione stem con Demucs (può richiedere qualche minuto)...")
            stems = load_single_file(args.input, work_dir=os.path.join(args.out, "_demucs"))
    _narrate(f"Caricati {len(stems.names())} stem: {', '.join(stems.names())} @ {stems.sample_rate}Hz")

    _narrate("Analizzo bpm, tonalità, genere, loudness e bilanciamento spettrale...")
    with metrics.stage("analysis", on_step=_narrate):
        analysis = analyze(stems)
    _narrate(
        f"BPM {analysis.bpm:.1f}  |  Tonalità {analysis.key_name}  |  Genere {analysis.genre.name}  |  "
        f"{analysis.mix_lufs:.1f} LUFS  |  Crest {analysis.mix_crest:.1f}"
    )

    prefs = run_wizard(analysis.genre.name, interactive=not args.non_interactive)

    reference_audio, reference_sr = None, None
    if args.reference:
        reference_audio, reference_sr = sf.read(args.reference, dtype="float32", always_2d=True)

    _narrate("Avvio il mix...")
    with metrics.stage("mix_render", on_step=_narrate):
        mixed = render_mix(stems, analysis, prefs, on_step=_narrate, reference=reference_audio, reference_sr=reference_sr)

    mix_path = os.path.join(args.out, "mix.wav")
    sf.write(mix_path, mixed, stems.sample_rate)
    _narrate(f"Mix salvato: {mix_path}")

    if prefs.do_mastering:
        _narrate("Avvio il mastering...")
        with metrics.stage("master_render", on_step=_narrate):
            if args.reference:
                master_path = os.path.join(args.out, "master.wav")
                render_master_reference(mix_path, args.reference, master_path, on_step=_narrate)
            else:
                mastered = render_master(
                    mixed, stems.sample_rate, analysis, platform=args.platform, on_step=_narrate,
                    reference=reference_audio, reference_sr=reference_sr,
                )
                master_path = os.path.join(args.out, "master.wav")
                sf.write(master_path, mastered, stems.sample_rate)
        _narrate(f"Master salvato: {master_path}")

    _narrate(f"Fatto. Tempo totale: {metrics.total_seconds():.1f}s")
    for name, seconds in metrics.slowest(3):
        _narrate(f"[METRIC] stage più lento: {name} ({seconds:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
