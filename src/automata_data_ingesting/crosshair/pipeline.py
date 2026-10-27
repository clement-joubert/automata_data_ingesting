"""Run Crosshair on an AUTOMATA project without editing the external repo."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from automata_data_ingesting.photogrammetry.pipeline import project_objects


RUNNER = Path(__file__).with_name("_runner.py")
SCRIPTS = {
    "segment": "hsi/segment_roi_birefnet.py",
    "cluster": "hsi/run_roi_clustering.py",
    "points": "photogrammetry/analyze_hsi_clusters.py",
}


def default_repo() -> Path:
    # Use the bundled version: the sibling checkout may use older entry points.
    root = Path(__file__).resolve().parents[3]
    return root / "third_party/automata_crosshair"


def require_file(path: Path) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or empty file: {path}")
    return path


def validate_hsi(obj: Path) -> None:
    raw = obj / "HSI/raw_data"
    capture = raw / "capture"
    cubes = sorted(p for p in capture.glob("*.raw")
                   if "DARK" not in p.name.upper() and "WHITE" not in p.name.upper())
    if len(cubes) != 1:
        raise ValueError(f"Expected one HSI acquisition in {capture}, found {len(cubes)}")
    require_file(cubes[0])
    require_file(cubes[0].with_suffix(".hdr"))
    # Upstream takes the first header independently; reject ambiguous pairings.
    headers = [p for p in capture.glob("*.hdr")
               if "DARK" not in p.name.upper() and "WHITE" not in p.name.upper()]
    if len(headers) != 1:
        raise ValueError(f"Expected one acquisition header in {capture}")
    metadata = sorted((raw / "metadata").glob("*.xml"))
    if len(metadata) != 1:
        raise ValueError(f"Expected one acquisition XML (datacube_angle) in {raw / 'metadata'}")
    ET.parse(require_file(metadata[0]))
    for prefix in ("REFLECTANCE_", "RGBVIEWFINDER_"):
        images = list((raw / "results").glob(f"{prefix}*.png"))
        if len(images) != 1:
            raise ValueError(f"Expected one {prefix}*.png in {raw / 'results'}")
        require_file(images[0])


def select_mesh(obj: Path, override: Path | None) -> Path:
    if override is not None:
        return require_file(override)
    return require_file(obj / "photogrammetry/processed_data/textured_mesh.glb")


def copy_runtime(repo: Path, runtime: Path) -> None:
    """Copy only Python sources; upstream fixed output paths stay temporary."""
    for folder in (Path(), Path("hsi"), Path("photogrammetry")):
        destination = runtime / folder
        destination.mkdir(parents=True, exist_ok=True)
        for source in (repo / folder).glob("*.py"):
            # Matplotlib 3.11 removed cm.get_cmap. pyplot.get_cmap keeps the
            # same (name, lut) interface, including discrete cluster palettes.
            # Apply compatibility only to this disposable copy of the scripts.
            code = source.read_text(encoding="utf-8")
            code = code.replace("plt.cm.get_cmap(", "plt.get_cmap(")
            code = code.replace(
                "    face_hits, ray_hits = mesh_norm.ray.intersects_id(",
                "    from _automata_rays import intersect_rays\n"
                "    face_hits, ray_hits = intersect_rays(mesh_norm,",
            )
            (destination / source.name).write_text(code, encoding="utf-8")
    shutil.copy2(Path(__file__).with_name("_rays.py"), runtime / "_automata_rays.py")


def publish(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, destination / path.name)


def process_object(obj: Path, *, repo: Path, python: str, step: str,
                   mesh: Path | None, units: str, overwrite: bool,
                   algorithm: str, xrf_only: bool, grid_size: int = 256,
                   ray_batch_size: int = 64) -> None:
    name = obj.name
    processed = obj / "HSI/processed_data"
    roi = processed / "roi"
    clusters = processed / "roi_clustered"
    targets = processed / "crosshair"
    stages = ("segment", "cluster", "points") if step == "all" else (step,)

    with tempfile.TemporaryDirectory(prefix="automata_crosshair_") as temp:
        work = Path(temp)
        runtime = work / "runtime"
        copy_runtime(repo, runtime)
        dataset = work / "dataset"
        artifact = dataset / name
        artifact.mkdir(parents=True)
        (artifact / "HSI").symlink_to(obj / "HSI", target_is_directory=True)
        # The point script's ROI directory is hardcoded relative to __file__.
        roi.mkdir(parents=True, exist_ok=True)
        runtime_roi = runtime / "hsi/output/roi"
        runtime_roi.parent.mkdir(parents=True, exist_ok=True)
        runtime_roi.symlink_to(roi, target_is_directory=True)

        def run(stage, flags):
            environment = dict(os.environ, AUTOMATA_RAY_BATCH_SIZE=str(ray_batch_size))
            subprocess.run(
                [python, str(RUNNER), "script", str(runtime), str(dataset), SCRIPTS[stage], *flags],
                cwd=runtime, check=True, env=environment,
            )

        mask = roi / f"{name}_mask.png"
        cluster_map = clusters / f"{name}_clusters.png"
        for stage in stages:
            print(f"[{name}] {stage}", flush=True)
            if stage == "segment":
                if overwrite or not mask.is_file():
                    output = work / "roi"
                    flags = ["--batch", "--hsi_only", "--output_dir", str(output)]
                    run(stage, flags)
                    require_file(output / mask.name)
                    publish(output, roi)
                # Upstream exits successfully even if the user skips/quits.
                require_file(mask)
            elif stage == "cluster":
                require_file(mask)
                if overwrite or not cluster_map.is_file():
                    output = work / "clusters"
                    run(stage, ["--dataset", str(dataset), "--roi", str(roi),
                                "--output", str(output), "--artifacts", name,
                                "--algorithm", algorithm])
                    require_file(output / cluster_map.name)
                    publish(output, clusters)
                require_file(cluster_map)
            else:
                require_file(mask)
                require_file(cluster_map)
                expected = [f"{name}_xrf.ply", f"{name}_xrf_report.json"]
                if not xrf_only:
                    expected += [f"{name}_raman.ply", f"{name}_raman_targets.json",
                                 f"{name}_hsi_clusters_regions.ply"]
                if not overwrite and all((targets / file).is_file() and
                                         (targets / file).stat().st_size > 0 for file in expected):
                    print(f"[{name}] Existing targets preserved", flush=True)
                    continue
                source = select_mesh(obj, mesh)
                mesh_dir = work / "mesh"
                mesh_dir.mkdir()
                converted = mesh_dir / "mesh_cm.obj"
                subprocess.run([python, str(RUNNER), "mesh", str(source), str(converted), units],
                               cwd=runtime, check=True)
                require_file(converted)
                photo = artifact / "photogrammetry"
                photo.mkdir()
                (photo / "raw_data").symlink_to(mesh_dir, target_is_directory=True)
                output = work / "targets"
                flags = ["--artifact", name, "--clusters-dir", str(clusters),
                         "--output", str(output), "--grid-size", str(grid_size)]
                if xrf_only:
                    flags.append("--xrf-only")
                run(stage, flags)
                for file in expected:
                    require_file(output / file)
                # Reports must refer to the original mesh, not the removed workspace.
                for report in output.glob("*.json"):
                    data = json.loads(report.read_text())
                    data.update(mesh=str(source), mesh_units=units, point_units="cm")
                    report.write_text(json.dumps(data, indent=2) + "\n")
                publish(output, targets)
        print(f"[{name}] Results: {processed}", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path_project", "--path-project", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=default_repo())
    parser.add_argument("--python", default=sys.executable,
                        help="Python environment with automata_crosshair dependencies.")
    parser.add_argument("--object", help="Process one XML-listed object (default: all).")
    parser.add_argument("--step", choices=["all", *SCRIPTS], default="all")
    parser.add_argument("--mesh", type=Path,
                        help="Override textured_mesh.glb (single object only).")
    parser.add_argument("--mesh-units", choices=["m", "cm", "mm"], default="m",
                        help="Source mesh units (default: metres, as exported by photogrammetry).")
    parser.add_argument("--algorithm", choices=["hdbscan", "kmeans", "gmm", "agglomerative", "optics"],
                        default="hdbscan")
    parser.add_argument("--xrf-only", action="store_true")
    parser.add_argument("--grid-size", type=int, default=256,
                        help="Face mapping resolution (default: 256; use 128 for fewer rays).")
    parser.add_argument("--ray-batch-size", type=int, default=64,
                        help="Maximum rays per intersection batch (default: 64).")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.grid_size < 2 or args.ray_batch_size < 1:
            raise ValueError("Grid size must be at least 2 and ray batch size must be positive.")
        project = args.path_project.expanduser().resolve(strict=True)
        repo = args.repo.expanduser().resolve(strict=True)
        for script in ("paths.py", *SCRIPTS.values()):
            require_file(repo / script)
        objects = project_objects(project)
        if args.object:
            objects = [obj for obj in objects if obj.name == args.object]
            if not objects:
                raise ValueError(f"Object not listed in project XML: {args.object}")
        if args.mesh and len(objects) != 1:
            raise ValueError("--mesh requires a single object; select it with --object.")
        mesh = args.mesh.expanduser().resolve(strict=True) if args.mesh else None
        python = args.python
        if Path(python).expanduser().is_file():
            python = str(Path(python).expanduser().absolute())
        # Validate every selected object before launching the interactive stage.
        for obj in objects:
            validate_hsi(obj)
            if args.step in {"all", "points"}:
                select_mesh(obj, mesh)
        for obj in objects:
            process_object(obj, repo=repo, python=python, step=args.step, mesh=mesh,
                           units=args.mesh_units, overwrite=args.overwrite,
                           algorithm=args.algorithm, xrf_only=args.xrf_only,
                           grid_size=args.grid_size, ray_batch_size=args.ray_batch_size)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"ERROR: Crosshair command failed (exit {error.returncode}). See output above.\n")
    return 0
