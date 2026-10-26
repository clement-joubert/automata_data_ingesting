"""
AUTOMATA ECCCH

Recursive SFTP uploads with strict host verification and no overwrites.
"""

from __future__ import annotations

import argparse
import errno
import getpass
import logging
from pathlib import Path, PurePosixPath
import stat
import tomllib

LOG = logging.getLogger(__name__)


def collect_dataset(data_root: Path, folder: str) -> tuple[Path, list[Path], list[Path]]:
    """
    Validate the source and reject links and special files before connecting.
    """

    root = data_root.expanduser().resolve(strict=True)
    candidate = root / folder

    # Check each component before resolve(), which would hide symlinks.
    if ".." in Path(folder).parts:
        raise ValueError("The dataset path must not contain '..'.")
    source = candidate.absolute()

    if not source.is_relative_to(root) or source == root:
        raise ValueError("Choose a folder inside data_root, not data_root itself.")
    
    for component in (source, *source.parents):
        if component == root:
            break
        if component.is_symlink():
            raise ValueError(f"Symbolic links are not allowed: {component}")
        
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"Dataset is not a directory: {source}")
    
    directories, files = [], []
    for path in sorted(source.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            directories.append(path.relative_to(source))
        elif stat.S_ISREG(mode):
            files.append(path.relative_to(source))
        else:
            raise ValueError(f"Only regular files and directories are allowed: {path}")
        
    return source, directories, files


def remote_attributes(sftp, path: PurePosixPath):
    try:
        return sftp.lstat(str(path))
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise OSError(f"Cannot inspect remote path {path}: {exc}") from exc


def ensure_remote_directory(sftp, path: PurePosixPath) -> None:
    """
    Create one directory inside an existing parent.
    """

    attributes = remote_attributes(sftp, path)

    if attributes is None:
        try:
            sftp.mkdir(str(path))
        except OSError as exc:
            raise OSError(f"Cannot create remote directory {path}: {exc}") from exc
    elif not stat.S_ISDIR(attributes.st_mode):
        raise ValueError(f"Remote path is not a regular directory: {path}")


def upload_dataset(sftp, source: Path, directories: list[Path], files: list[Path],
                   destination: PurePosixPath) -> None:
    """
    Upload directly to final filenames. Failed uploads may leave partial files.

    Keep the source unchanged and avoid concurrent uploads to this destination.
    """

    # Start at the configured directory, without probing shared server ancestors.
    try:
        sftp.chdir(str(destination.parent))
    except OSError as exc:
        raise OSError(
            f"Cannot access remote_root {destination.parent}: {exc}. "
            "Use an existing directory visible to your SFTP account."
        ) from exc
    
    ensure_remote_directory(sftp, destination)
    for relative in directories:
        ensure_remote_directory(sftp, destination / relative.as_posix())

    # Refuse known collisions before transferring any file.
    for relative in files:
        target = destination / relative.as_posix()
        if remote_attributes(sftp, target) is not None:
            raise FileExistsError(f"Remote file already exists: {target}")
        
    for index, relative in enumerate(files, 1):
        local = source / relative
        target = destination / relative.as_posix()
        LOG.info("[%d/%d] Uploading %s", index, len(files), relative)

        try:
            sftp.put(str(local), str(target), confirm=False)
        except OSError as exc:
            raise OSError(
                f"Cannot write remote file {target}: {exc}. "
                "Check server write permissions and storage quota. "
                "A partial file may remain."
            ) from exc
        
        try:
            remote_size = sftp.stat(str(target)).st_size
        except OSError as exc:
            raise OSError(f"File sent but cannot verify remote size for {target}: {exc}") from exc
        
        if remote_size != local.stat().st_size:
            raise OSError(f"Remote size does not match local file: {target}")
        
        LOG.info("[%d/%d] Uploaded %s", index, len(files), relative)


def connect(config: dict, *, password: str | None = None,
            passphrase: str | None = None):
    """
    Connect using an SSH agent/key, or an explicitly prompted password.
    """

    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("Install the uploader first: python -m pip install -e .") from exc
    
    client = paramiko.SSHClient()
    try:
        client.load_system_host_keys()

        if config.get("known_hosts"):
            client.load_host_keys(str(Path(config["known_hosts"]).expanduser()))

        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        timeout = float(config.get("timeout", 30))
        client.connect(
            hostname=config["host"], port=int(config.get("port", 22)),
            username=config["username"],
            key_filename=(str(Path(config["key_file"]).expanduser())
                          if config.get("key_file") else None),
            password=password, passphrase=passphrase,
            allow_agent=password is None, look_for_keys=password is None,
            timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
            channel_timeout=timeout,
        )

        transport = client.get_transport()

        if transport is not None:
            transport.set_keepalive(30)

        return client
    
    except Exception:
        client.close()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="Generated folder relative to --data-root")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, required=True, help="SFTP TOML configuration")
    parser.add_argument("--dry-run", action="store_true", help="List files without connecting")
    parser.add_argument("--ask-password", action="store_true", help="Prompt for an SFTP password")
    parser.add_argument("--ask-passphrase", action="store_true", help="Prompt for an SSH key passphrase")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    try:
        with args.config.expanduser().open("rb") as stream:
            config = tomllib.load(stream)["sftp"]

        for key in ("host", "username", "remote_root"):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise ValueError(f"Set sftp.{key} in the configuration.")
            
        if any(key in config for key in ("password", "passphrase")):
            raise ValueError("Do not store passwords in TOML; use the prompt options.")
        
        remote_root = PurePosixPath(config["remote_root"])
        if not remote_root.is_absolute() or ".." in remote_root.parts:
            raise ValueError("remote_root must be an absolute SFTP path without '..'.")
        
        source, directories, files = collect_dataset(args.data_root, args.folder)
        destination = remote_root / source.name
        LOG.info("%s -> %s:%s (%d files)", source, config["host"], destination, len(files))

        # For testing before real connection
        if args.dry_run:
            for relative in directories:
                LOG.info("Directory: %s", destination / relative.as_posix())
            for relative in files:
                LOG.info("File: %s", destination / relative.as_posix())
            LOG.info("Dry run complete; no connection made.")
            return 0
        
        password = getpass.getpass("SFTP password: ") if args.ask_password else None
        passphrase = getpass.getpass("SSH key passphrase: ") if args.ask_passphrase else None

        with connect(config, password=password, passphrase=passphrase) as client:
            with client.open_sftp() as sftp:
                sftp.get_channel().settimeout(float(config.get("timeout", 30)))
                upload_dataset(sftp, source, directories, files, destination)
        LOG.info("Upload complete: %d files.", len(files))

        return 0
    
    except KeyboardInterrupt:
        LOG.error("Upload interrupted; some files may already have been uploaded.")
        return 130
    
    except Exception as exc:
        LOG.error("Upload failed: %s", exc)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
