"""Batch processing: iterate over a directory of projects and process each
one through the full RedLine pipeline (load -> analyze -> mix -> master).

Each subdirectory of `batch_dir` that contains audio files is treated as a
project. Results are collected into a list of dicts and saved as JSON."""

from __future__ import annotations

import json
import os
import time
from typing import Callable

import soundfile as sf

from .input_loader import load_auto, AUDIO_EXTENSIONS
from .analyze import analyze
from .wizard import run_wizard
from .mixengine import render_mix
from .masterengine import render_master
from .dsp_utils import finalize_for_export


def _find_projects(batch_dir: str) -> list[str]:
    """Scan batch_dir for subdirectories that contain audio files.
    Returns sorted list of subdirectory names (basenames)."""
    if not os.path.isdir(batch_dir):
        raise ValueError(f"batch_dir not found: {batch_dir}")
    projects: list[str] = []
    for entry in sorted(os.listdir(batch_dir)):
        sub = os.path.join(batch_dir, entry)
        if not os.path.isdir(sub):
            continue
        # Check if this subdirectory has any audio files
        has_audio = False
        for root, _dirs, files in os.walk(sub):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in AUDIO_EXTENSIONS:
                    has_audio = True
                    break
            if has_audio:
                break
        if has_audio:
            projects.append(entry)
    return projects


class BatchProcessor:
    """Processes multiple projects in a batch directory.

    Each subdirectory of batch_dir that contains audio files is treated as a
    project. The pipeline (load_auto -> analyze -> render_mix -> render_master)
    runs for each project independently. Failures in one project do not block
    others.
    """

    def __init__(self, on_step: Callable[[str], None] | None = None):
        self.on_step = on_step or (lambda msg: None)

    def run(
        self,
        batch_dir: str,
        out_dir: str,
        *,
        platform: str = "auto",
        non_interactive: bool = True,
        reference: str | None = None,
        genre_override: str | None = None,
    ) -> list[dict]:
        """Process all projects found in batch_dir.

        Args:
            batch_dir: Directory containing project subdirectories.
            out_dir: Output directory for mix/master files and batch_report.json.
            platform: Target platform for mastering.
            non_interactive: Skip wizard, use default preferences.
            reference: Optional reference track path (applied to ALL projects).
            genre_override: Optional genre selection applied to every project
                (overrides the measured genre; unknown names fall back).

        Returns:
            List of result dicts, one per project, with keys:
                project, ok, mix_path, master_path, error, duration_sec
        """
        projects = _find_projects(batch_dir)
        if not projects:
            self.on_step(f"Nessun progetto trovato in {batch_dir}")
            return []

        os.makedirs(out_dir, exist_ok=True)
        results: list[dict] = []
        total_start = time.perf_counter()

        for i, project_name in enumerate(projects, 1):
            self.on_step(f"\n[{i}/{len(projects)}] Progetto: {project_name}")
            project_dir = os.path.join(batch_dir, project_name)
            project_out = os.path.join(out_dir, project_name)
            os.makedirs(project_out, exist_ok=True)

            result: dict = {
                "project": project_name,
                "ok": False,
                "mix_path": None,
                "master_path": None,
                "error": None,
                "duration_sec": 0.0,
            }
            proj_start = time.perf_counter()

            try:
                # Step 1: Load audio
                self.on_step("  Carico l'audio...")
                stems = load_auto(
                    project_dir,
                    work_dir=os.path.join(project_out, "_demucs"),
                    on_step=lambda msg: self.on_step(f"    {msg}"),
                )
                self.on_step(
                    f"  Caricati {len(stems.names())} stem: "
                    f"{', '.join(stems.names())} @ {stems.sample_rate}Hz"
                )

                # Step 2: Analyze (genre_override known upfront in batch mode)
                self.on_step("  Analizzo...")
                analysis = analyze(stems, genre_override=genre_override)
                self.on_step(
                    f"  BPM {analysis.bpm:.1f} | Tonalita {analysis.key_name} | "
                    f"Genere {analysis.genre.name} | {analysis.mix_lufs:.1f} LUFS"
                )

                # Step 3: Wizard (non-interactive in batch mode)
                prefs = run_wizard(analysis.genre.name, interactive=False)

                # Step 4: Mix
                self.on_step("  Mix...")
                mixed = render_mix(
                    stems, analysis, prefs,
                    on_step=lambda msg: self.on_step(f"    {msg}"),
                )

                mix_path = os.path.join(project_out, "mix.wav")
                sf.write(mix_path, finalize_for_export(mixed), stems.sample_rate, subtype="PCM_24")
                result["mix_path"] = mix_path
                self.on_step(f"  Mix salvato: {mix_path}")

                # Step 5: Master (if enabled)
                if prefs.do_mastering:
                    self.on_step("  Mastering...")
                    if reference:
                        from .masterengine import render_master_reference

                        master_path = os.path.join(project_out, "master.wav")
                        render_master_reference(
                            mix_path, reference, master_path,
                            on_step=lambda msg: self.on_step(f"    {msg}"),
                        )
                        result["master_path"] = master_path
                    else:
                        mastered = render_master(
                            mixed, stems.sample_rate, analysis,
                            platform=platform,
                            on_step=lambda msg: self.on_step(f"    {msg}"),
                        )
                        master_path = os.path.join(project_out, "master.wav")
                        sf.write(master_path, finalize_for_export(mastered), stems.sample_rate, subtype="PCM_24")
                        result["master_path"] = master_path
                    self.on_step(f"  Master salvato: {master_path}")

                result["ok"] = True

            except Exception as e:
                self.on_step(f"  ERRORE: {e}")
                result["error"] = str(e)

            elapsed = time.perf_counter() - proj_start
            result["duration_sec"] = round(elapsed, 2)
            results.append(result)

        # Summary
        total_elapsed = time.perf_counter() - total_start
        successes = sum(1 for r in results if r["ok"])
        failures = len(results) - successes
        self.on_step(
            f"\nBatch completato: {successes} successi, {failures} fallimenti "
            f"in {total_elapsed:.1f}s"
        )

        # Save report
        report_path = os.path.join(out_dir, "batch_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "batch_dir": batch_dir,
                    "out_dir": out_dir,
                    "total_projects": len(results),
                    "successes": successes,
                    "failures": failures,
                    "total_duration_sec": round(total_elapsed, 2),
                    "results": results,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        self.on_step(f"Report salvato: {report_path}")

        return results
