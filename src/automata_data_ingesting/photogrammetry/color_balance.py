"""Convert an object's RAW acquisitions using automata_photogrammetry."""

from pathlib import Path
import shutil
import subprocess


def color_balance(raw_dir: Path, processed_dir: Path, *, repo: Path,
                  python: str, matrix: Path, dark: Path | None,
                  saturation_threshold: float = 4096, overwrite: bool = False) -> None:
    """Write PNGs and preserve acquisition sidecars for robot pose lookup.

    The external batch command returns nonzero if any acquisition fails. Never
    continue to reconstruction in that case, even if some PNGs were written.
    """
    images = processed_dir / "images"
    command = [
        python, "-m", "calibration.color.batch_color_balance",
        "--input-dir", str(raw_dir), "--output-dir", str(images),
        "--path-correction-matrix", str(matrix),
        "--saturation-threshold", str(saturation_threshold),
    ]
    if dark is not None:
        command += ["--path-dark", str(dark)]
    if overwrite:
        command.append("--overwrite")
    subprocess.run(command, cwd=repo, check=True)

    # Only copy metadata for images that actually exist (exclude e.g. a dark
    # frame skipped by batch_color_balance). Preserve JSON content verbatim.
    for sidecar in sorted(raw_dir.glob("*.json")):
        if (images / f"{sidecar.stem}.png").is_file():
            destination = images / sidecar.name
            if overwrite or not destination.exists():
                shutil.copy2(sidecar, destination)
