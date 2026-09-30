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
from .analyze import analyze, apply_genre_override
from .wizard import run_wizard
from .mixengine import render_mix
from .masterengine import render_master, render_master_reference
from .dsp_utils import finalize_for_export
from .metrics import Metrics
from .batch import BatchProcessor


def _narrate(msg: str) -> None:
    print(f"[RedLine] {msg}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RedLine Engine — standalone mix + mastering")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder", help="A single file or folder — the right loading mode is auto-detected")
    src.add_argument("--stems-dir", help="Folder with an arbitrary number of named stem files")
    src.add_argument("--vocals", help="Path to a pre-mixed vocals track (pair with --instrumental)")
    src.add_argument("--input", help="Single mixed file — auto-separated via Demucs")
    src.add_argument("--batch", help="Directory of project subfolders to process in batch mode")
    p.add_argument("--instrumental", help="Path to a pre-mixed instrumental track (pairs with --vocals)")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--reference", help="Optional reference track for reference-matched mastering")
    p.add_argument("--platform", default="auto", choices=["auto", "spotify", "apple", "youtube", "club"])
    p.add_argument("--non-interactive", action="store_true", help="Skip the wizard, use default preferences")
    p.add_argument("--export-buses", action="store_true", help="Also export intermediate buses (vocal_main, vocal_doubles, music, parallel, reverb) as separate WAV files")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.vocals and not args.instrumental:
        print("--vocals richiede anche --instrumental", file=sys.stderr)
        return 1

    if args.batch:
        os.makedirs(args.out, exist_ok=True)
        processor = BatchProcessor(on_step=_narrate)
        processor.run(
            batch_dir=args.batch,
            out_dir=args.out,
            platform=args.platform,
            non_interactive=args.non_interactive,
            reference=args.reference,
        )
        return 0

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

    # The wizard runs after analyze() (it needs the measured genre as its
    # default), so a genre the user picked there is applied to the already
    # computed AnalysisResult here -- before any render consumes it.
    apply_genre_override(analysis, prefs.genre_override)
    if prefs.genre_override:
        _narrate(f"Genere impostato dall'utente: {analysis.genre.name}")

    reference_audio, reference_sr = None, None
    if args.reference:
        reference_audio, reference_sr = sf.read(args.reference, dtype="float32", always_2d=True)

    _narrate("Avvio il mix...")
    if args.export_buses:
        from .bus_exporter import export_buses
        with metrics.stage("mix_render", on_step=_narrate):
            buses = export_buses(stems, analysis, prefs, on_step=_narrate, on_event=lambda _e: None)
        mixed = buses.full_mix
        bus_files = {
            "vocal_main": buses.vocal_main,
            "vocal_doubles": buses.vocal_doubles,
            "music_bus": buses.music,
            "parallel_bus": buses.parallel,
            "reverb_bus": buses.reverb,
        }
        for bus_name, bus_audio in bus_files.items():
            if bus_audio is not None:
                bus_path = os.path.join(args.out, f"{bus_name}.wav")
                sf.write(bus_path, finalize_for_export(bus_audio), stems.sample_rate, subtype="PCM_24")
                _narrate(f"Bus esportato: {bus_path}")
    else:
        with metrics.stage("mix_render", on_step=_narrate):
            mixed = render_mix(stems, analysis, prefs, on_step=_narrate, reference=reference_audio, reference_sr=reference_sr)

    mix_path = os.path.join(args.out, "mix.wav")
    sf.write(mix_path, finalize_for_export(mixed), stems.sample_rate, subtype="PCM_24")
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
                    prefs=prefs,
                )
                master_path = os.path.join(args.out, "master.wav")
                sf.write(master_path, finalize_for_export(mastered), stems.sample_rate, subtype="PCM_24")
        _narrate(f"Master salvato: {master_path}")

    _narrate(f"Fatto. Tempo totale: {metrics.total_seconds():.1f}s")
    for name, seconds in metrics.slowest(3):
        _narrate(f"[METRIC] stage più lento: {name} ({seconds:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
