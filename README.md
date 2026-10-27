<div align="center">
# AUTOMATA · Data ingestion

Prepare acquisitions, reconstruct objects, calculate measurement points, and upload to Archeogrid.

</div>

| Step | Task | Command |
| :---: | --- | --- |
| 1 | [Data tree and metadata](#step-1-generate-the-data-tree-and-metadata) | `automata-metadata` |
| 2 | [Photogrammetry](#step-2-launch-photogrammetry) | `automata-photogrammetry` |
| 3 | [HSI registration and points](#step-3-launch-hsi-registration-and-point-calculation) | `automata-crosshair` |
| 4 | [Archeogrid upload](#step-4-upload-to-archeogrid) | `automata-upload` |

## Setup

**Requirements:** Python 3.11+ and Tkinter for the metadata UI. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[processing]"
```

On Windows, create the environment with `py -3 -m venv .venv` and run commands
from `.venv/Scripts/` without activation.

The `processing` extra installs the Python dependencies for photogrammetry and HSI.
For metadata and upload only, use `python -m pip install -e .`.
Tkinter, COLMAP/OpenMVS, OpenGL, and the NVIDIA driver are installed separately.

The current working environment uses Python 3.14.4. Dependency ranges in
`pyproject.toml` describe supported packages; they are not an exact environment lock.

## Run the workflow

```bash
automata-pipeline --path_project data/20261019_QB1stTEST --ask-password
```

Runs steps 1–4 in order and stops on any failure. Metadata entry and ROI selection
remain interactive. In the metadata UI, export the named batch under `data/`,
then close the UI. Acquisition files and edited photogrammetry configs must be
in place before step 2; see the individual steps below.

For a new project, use `--to-step 1` to create the tree first. Add the data and
prepare the configs, then resume:

```bash
automata-pipeline --path_project data/20261019_QB1stTEST --from-step 2 --ask-password
```

Use `--from-step 3` to resume at HSI processing, or `--to-step 3` to stop before
uploading. `--config` defaults to `configs/sftp.toml` and is required for uploads.
Pass `--path-dark` and `--path-correction-matrix` as needed. Separate environments
can be selected with `--metadata-python`, `--photogrammetry-python`, and
`--crosshair-python`. The individual commands below remain available.
You can also run `python -m automata_data_ingesting`.

## Step 1: Generate the data tree and metadata

```bash
automata-metadata
```

Enter the batch and object metadata in the UI, then select **Export XML + folders**
and choose this repository's `data/` as the parent directory. For example:

```text
data/20261019_QB1stTEST/
├── 20261019_QB1stTEST.xml
├── Calibration/
└── TestMonteLupo/
    ├── photogrammetry/{raw_data,processed_data,paradata}/
    ├── HSI/{raw_data,processed_data,paradata}/
    └── …
```

Use simple object codes such as `TestMonteLupo` so XML object names match their
folder names. Place acquisitions in the corresponding `raw_data/` folders.

## Step 2: Launch photogrammetry

**Requirements:** `automata_photogrammetry` dependencies and COLMAP/OpenMVS.
The sibling repo is used by default, falling back to the bundled submodule.
Use `--repo` or `--python` to select another checkout or processing environment.

Put camera RAW files and matching JSON sidecars in `photogrammetry/raw_data/`.
**Configure:** Create the per-object configurations:

```bash
automata-photogrammetry --path_project data/20261019_QB1stTEST --setup-only
```

Edit `photogrammetry/processed_data/config.yaml` for each object: set calibration,
bounding-box paths, and robot poses. Relative paths start at `processed_data`;
use `robot_poses.metadata_dir: images` for copied sidecars.

**Run:**

```bash
automata-photogrammetry \
  --path_project data/20261019_QB1stTEST \
  --path-dark /path/to/color_calibration.raw
```

**Output:** Color balancing writes PNGs and JSONs to `processed_data/images/`, then reconstruction
produces `processed_data/textured_mesh.glb`. The matrix defaults to the external
repo's `ColorCalib.txt`; saturation defaults to `4096`. Use
`--path-correction-matrix` to change the matrix. Omitting `--path-dark` disables
dark-frame correction.

Use `--color-only`, `--reconstruct-only`, or `--overwrite` as needed.

## Step 3: Launch HSI registration and point calculation

**Requirements:** The `processing` extra above and OpenGL.

Provide one HSI acquisition per object:

```text
HSI/raw_data/
├── capture/       # Acquisition .raw + matching .hdr; dark/white references allowed
├── metadata/      # Acquisition XML containing datacube_angle
└── results/       # One REFLECTANCE_*.png and one RGBVIEWFINDER_*.png
```

```bash
automata-crosshair --path_project data/20261019_QB1stTEST
```

Draw the ROI box, press **Enter** to segment, then **S** to save. Clustering, registration
on the photogrammetry mesh, and XRF/Raman point generation follow automatically.

**Output:** Results go into `HSI/processed_data/{roi,roi_clustered,crosshair}/`, including PLYs
and JSON point coordinates in centimetres.

Use `--python` for another environment, `--object TestMonteLupo` for one object,
or `--overwrite` to recompute. Resume individual stages with
`--step segment|cluster|points`. Ray casting uses batches of 64; reduce
`--ray-batch-size` if memory is limited. `--grid-size 128` lowers mapping resolution.
Source meshes default to metres; override with `--mesh-units cm|mm`.

## Step 4: Upload to Archeogrid

Copy `configs/sftp.example.toml` to `configs/sftp.toml`. Set the server, username,
and existing writable `remote_root`; keep passwords out of this file.
Before the first upload, connect with `sftp -P 22 username@hostname` and verify
the server fingerprint with its administrator.

```bash
automata-upload 20261019_QB1stTEST --config configs/sftp.toml --ask-password
```

Uploads the complete project folder under `remote_root`. Use `--dry-run` to preview.
For SSH keys, omit `--ask-password`, configure `key_file`, and use
`--ask-passphrase` if encrypted. Existing files are refused; inspect partial
uploads before retrying. Keep the source unchanged during upload.
