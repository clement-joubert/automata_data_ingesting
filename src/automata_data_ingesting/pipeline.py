"""Run metadata, photogrammetry, HSI processing and upload in order."""

import argparse
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from .photogrammetry.pipeline import project_objects


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path_project", "--path-project", type=Path, required=True)
    parser.add_argument("--from-step", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--to-step", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--config", type=Path, default=Path("configs/sftp.toml"))
    parser.add_argument("--ask-password", action="store_true")
    parser.add_argument("--ask-passphrase", action="store_true")
    parser.add_argument("--metadata-python", help="Python with Tkinter (default: current Python).")
    parser.add_argument("--photogrammetry-python", help="Python with photogrammetry dependencies.")
    parser.add_argument("--crosshair-python", help="Python with Crosshair dependencies.")
    parser.add_argument("--photogrammetry-repo", type=Path)
    parser.add_argument("--crosshair-repo", type=Path)
    parser.add_argument("--path-dark", type=Path)
    parser.add_argument("--path-correction-matrix", type=Path)
    parser.add_argument("--grid-size", type=int, default=256)
    parser.add_argument("--ray-batch-size", type=int, default=64)
    parser.add_argument("--overwrite", action="store_true",
                        help="Recompute images and HSI results; does not overwrite remote files.")
    args = parser.parse_args(argv)

    def python_path(value):
        if value is None:
            return sys.executable
        path = Path(value).expanduser()
        # Preserve venv symlinks rather than resolving to the system Python.
        return str(path.absolute()) if path.is_file() else value

    project = args.path_project.expanduser().resolve()
    config = args.config.expanduser().resolve()
    base = [sys.executable, "-m"]
    project_flags = ["--path_project", str(project)]
    photo = [*base, "automata_data_ingesting.photogrammetry", *project_flags]
    crosshair = [*base, "automata_data_ingesting.crosshair", *project_flags,
                "--grid-size", str(args.grid_size), "--ray-batch-size", str(args.ray_batch_size)]
    for command, python, repo in (
        (photo, args.photogrammetry_python, args.photogrammetry_repo),
        (crosshair, args.crosshair_python, args.crosshair_repo),
    ):
        if python:
            command += ["--python", python_path(python)]
        if repo:
            command += ["--repo", str(repo.expanduser().resolve())]
        if args.overwrite:
            command.append("--overwrite")
    for option, path in (("--path-dark", args.path_dark),
                         ("--path-correction-matrix", args.path_correction_matrix)):
        if path:
            photo += [option, str(path.expanduser().resolve())]
    upload = [*base, "automata_data_ingesting.uploading", project.name,
              "--data-root", str(project.parent), "--config", str(config)]
    if args.ask_password:
        upload.append("--ask-password")
    if args.ask_passphrase:
        upload.append("--ask-passphrase")
    metadata = Path(__file__).parent / "metadata/SoftMetadata_ajoutAATORCID.py"
    commands = {
        1: ("Metadata UI", [python_path(args.metadata_python), str(metadata)]),
        2: ("Photogrammetry", photo),
        3: ("HSI registration and points", crosshair),
        4: ("Archeogrid upload", upload),
    }

    step = args.from_step
    try:
        if args.from_step > args.to_step:
            raise ValueError("--from-step must not be greater than --to-step.")
        if args.grid_size < 2 or args.ray_batch_size < 1:
            raise ValueError("Grid size must be at least 2 and ray batch size must be positive.")
        if args.to_step == 4 and not config.is_file():
            raise ValueError(f"Missing SFTP config: {config}. Configure it or use --to-step 3.")
        for step in range(args.from_step, args.to_step + 1):
            label, command = commands[step]
            print(f"\nStep {step}/4: {label}", flush=True)
            if step == 1:
                print(f"Export batch '{project.name}' under {project.parent}, then close the UI.", flush=True)
            else:
                objects = project_objects(project)
                if step == 2:
                    for obj in objects:
                        path = obj / "photogrammetry/processed_data/config.yaml"
                        if not path.is_file():
                            raise ValueError(
                                f"Missing {path}. Run automata-photogrammetry --path_project "
                                f'"{project}" --setup-only, edit the configs, then resume with --from-step 2.'
                            )
            subprocess.run(command, check=True)
            if step == 1:
                # Closing the UI without exporting must not start processing.
                project_objects(project)
        print(f"\nCompleted steps {args.from_step}–{args.to_step}: {project}", flush=True)
        return 0
    except subprocess.CalledProcessError as error:
        print(f"ERROR: Step {step} failed (exit {error.returncode}). Later steps were not run. "
              f"After fixing the error, resume with --from-step {step}.", file=sys.stderr)
        return 1
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\nInterrupted at step {step}. Inspect partial results before resuming.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
