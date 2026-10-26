# AUTOMATA data ingestion

Tools for metadata creation, photogrammetry, HSI registration, and transfer to Archeogrid.

## Setup

Requires Python 3.11+. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp configs/sftp.example.toml configs/sftp.toml
```

Edit `configs/sftp.toml` with your server, username, and `remote_root`.
The remote directory must already exist and be writable. This configuration is ignored by Git; keep passwords out of it.

Before the first upload, connect once and verify the server fingerprint with its administrator before accepting it:

```bash
sftp -P 22 your_username@sftp.example.org
```

Use your configured hostname and port, then exit with `bye`.

## Upload

Upload a generated folder from `data/`, preserving its structure:

```bash
automata-upload 20260610_APetra_Rhyolites --config configs/sftp.toml --ask-password
```

The destination is `<remote_root>/20260610_APetra_Rhyolites/`.
Add `--dry-run` to preview without connecting. For SSH key authentication, omit `--ask-password`; set `key_file` if needed and use `--ask-passphrase` for an encrypted key.

Existing files are refused. Failed uploads may leave partial files; inspect the destination before retrying. Keep the source unchanged and avoid concurrent uploads to the same destination. This transfers files only; it does not trigger Archeogrid ingestion.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
