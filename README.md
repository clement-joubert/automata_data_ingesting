# AUTOMATA data ingestion

Metadata, photogrammetry, HSI registration, and uploads to Archeogrid.

## Setup

Requires Python 3.11+. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp configs/sftp.example.toml configs/sftp.toml
```

On Windows, create the environment with `py -3 -m venv .venv` and run commands
from `.venv/Scripts/` without activation.

## Upload

Set the server, username, and existing writable `remote_root` in
`configs/sftp.toml`. Keep passwords out of this file. Before uploading, connect
with `sftp -P 22 username@hostname` and verify the server fingerprint with its
administrator.

```bash
automata-upload 20260610_APetra_Rhyolites --config configs/sftp.toml --ask-password
```

Uploads `data/20260610_APetra_Rhyolites/` to the same folder under `remote_root`.
Use `--dry-run` to preview. For SSH keys, omit `--ask-password`; configure
`key_file` and use `--ask-passphrase` if encrypted.

Existing files are refused. Inspect partial uploads before retrying, and avoid
changing the source or uploading concurrently to the same destination.

## Photogrammetry

Requires the `automata_photogrammetry` dependencies and COLMAP/OpenMVS.
The sibling repo is used by default, with `third_party/automata_photogrammetry`
as fallback. Override with `--repo`; select its Python environment with `--python`.

Place RAW files and matching JSON sidecars in:

```text
data/20261019_QB1stTEST/
├── 20261019_QB1stTEST.xml
└── TestMonteLupo/photogrammetry/raw_data/
    ├── capture_001.raw
    ├── capture_001.json
    └── …
```

The XML lists object folders using `po_name` in the
`https://altag3d.huma-num.fr/data` namespace. All listed objects are processed.

Create the configurations:

```bash
automata-photogrammetry --path_project data/20261019_QB1stTEST --setup-only
```

Edit each object's `photogrammetry/processed_data/config.yaml`: set calibration,
bounding-box paths, and robot pose settings. Relative config paths start at
`processed_data`; use `robot_poses.metadata_dir: images` for copied sidecars.

Run color balancing and reconstruction:

```bash
automata-photogrammetry \
  --path_project data/20261019_QB1stTEST \
  --path-dark /path/to/color_calibration_wp_1.raw \
  --overwrite
```

The matrix defaults to the external repo's `ColorCalib.txt` (override with
`--path-correction-matrix`); saturation defaults to `4096`. Omit `--path-dark`
to disable dark-frame correction.

Corrected PNGs and JSONs go into `processed_data/images/`; reconstruction writes
under `processed_data/`, including `textured_mesh.glb`. Existing images and
sidecars are preserved unless `--overwrite` is given. Failed color batches stop
reconstruction.

Use `--color-only` or `--reconstruct-only` to run one stage.
