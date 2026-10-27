"""Color balance RAW acquisitions, then run the external reconstruction CLI."""

import argparse
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from .color_balance import color_balance


def default_repo() -> Path:
    root = Path(__file__).resolve().parents[3]
    sibling = root.parent / "automata_photogrammetry"
    return sibling if sibling.is_dir() else root / "third_party/automata_photogrammetry"


def project_objects(project: Path) -> list[Path]:
    """Read the same XML object list used by the reconstruction pipeline."""
    xml = project / f"{project.name}.xml"
    root = ET.parse(xml).getroot()
    names = [element.text.strip() for element in
             root.findall(".//{https://altag3d.huma-num.fr/data}po_name")
             if element.text and element.text.strip()]
    if not names:
        raise ValueError(f"No nonempty po_name objects in {xml}")
    objects = []
    for name in names:
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(f"Object name must be a directory name: {name!r}")
        path = (project / name).resolve()
        if not path.is_relative_to(project):
            raise ValueError(f"Object directory is outside the project: {path}")
        if path in objects:
            raise ValueError(f"Duplicate object name: {name}")
        objects.append(path)
    return objects


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path_project", "--path-project", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=default_repo(),
                        help="External automata_photogrammetry repo (default: sibling, then submodule).")
    parser.add_argument("--python", default=sys.executable,
                        help="Python executable with the photogrammetry dependencies installed.")
    parser.add_argument("--path-correction-matrix", type=Path,
                        help="Default: ColorCalib.txt in the external repo.")
    parser.add_argument("--path-dark", type=Path)
    parser.add_argument("--saturation-threshold", type=float, default=4096)
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace existing corrected images and their JSON sidecars.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--color-only", action="store_true")
    mode.add_argument("--reconstruct-only", action="store_true")
    mode.add_argument("--setup-only", action="store_true",
                      help="Create upstream per-object configs for editing, then exit.")
    args = parser.parse_args(argv)

    try:
        project = args.path_project.expanduser().resolve(strict=True)
        repo = args.repo.expanduser().resolve(strict=True)
        objects = project_objects(project)
        if not (repo / "main.py").is_file():
            raise ValueError(f"Missing photogrammetry entry point: {repo / 'main.py'}")
        # Resolve relative user paths before changing cwd to the external repo.
        python = args.python
        if Path(python).expanduser().is_file():
            # Keep a venv's executable path; resolve() could follow its symlink
            # to the system interpreter and lose the virtual environment.
            python = str(Path(python).expanduser().absolute())
        command = [python, "main.py", "--path_project", str(project)]
        if args.setup_only:
            subprocess.run(command + ["--setup_only"], cwd=repo, check=True)
            return 0

        if not args.reconstruct_only:
            matrix = (args.path_correction_matrix or repo / "ColorCalib.txt").expanduser().resolve(strict=True)
            dark = args.path_dark.expanduser().resolve(strict=True) if args.path_dark else None
            if not matrix.is_file() or (dark is not None and not dark.is_file()):
                raise ValueError("Correction matrix and dark frame must be files.")
            if not math.isfinite(args.saturation_threshold) or args.saturation_threshold <= 0:
                raise ValueError("Saturation threshold must be positive and finite.")
            # Check all objects before writing any corrected images.
            for obj in objects:
                raw = obj / "photogrammetry/raw_data"
                if not raw.is_dir() or not any(raw.glob("*.json")):
                    raise ValueError(f"Expected RAW files with JSON sidecars in {raw}")
            for obj in objects:
                print(f"Color balancing {obj.name}", flush=True)
                color_balance(
                    obj / "photogrammetry/raw_data",
                    obj / "photogrammetry/processed_data",
                    repo=repo, python=python, matrix=matrix, dark=dark,
                    saturation_threshold=args.saturation_threshold,
                    overwrite=args.overwrite,
                )

        if not args.color_only:
            for obj in objects:
                images = obj / "photogrammetry/processed_data/images"
                if not images.is_dir() or sum(
                    p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
                    and not p.name.lower().endswith(".mask.png") for p in images.rglob("*")
                ) < 2:
                    raise ValueError(f"At least two corrected photographs are required in {images}")
                config = obj / "photogrammetry/processed_data/config.yaml"
                if not config.is_file():
                    raise ValueError(f"Missing {config}. Run --setup-only and edit calibration/box paths first.")
            subprocess.run(command, cwd=repo, check=True)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"ERROR: Photogrammetry command failed (exit {error.returncode}). See output above.\n")
    return 0
