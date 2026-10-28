"""Subprocess bridge; runs with the external repo's Python environment."""

from pathlib import Path
import runpy
import sys


def export_mesh(source, destination, units):
    import numpy as np
    import trimesh

    mesh = trimesh.load(source, force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError(f"No triangle mesh in {source}")
    mesh.apply_scale({"m": 100.0, "cm": 1.0, "mm": 0.1}[units])
    extent = float(np.max(mesh.extents))
    # Crosshair guesses units from the extent. Outside this range it would
    # rescale an already centimetre-scaled mesh and return incorrect points.
    if not np.isfinite(mesh.vertices).all() or not 0.5 <= extent <= 100:
        raise ValueError("Crosshair requires a mesh spanning 0.5–100 cm; check --mesh-units.")
    mesh.export(destination, include_texture=False, include_color=False)


def main():
    mode, *arguments = sys.argv[1:]
    if mode == "mesh":
        export_mesh(*arguments)
        return
    runtime, dataset, script, *flags = arguments
    sys.path.insert(0, runtime)
    import paths

    # Some upstream entry points have no --dataset option.
    paths.DATASET_ROOT = Path(dataset)
    entry = str(Path(runtime) / script)
    sys.argv = [entry, *flags]
    runpy.run_path(entry, run_name="__main__")


if __name__ == "__main__":
    main()
