"""Content signatures used to invalidate cached dashboard inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def files_content_signature(paths: Iterable[Path]) -> str:
    """Hash file identities and contents so cache invalidation never relies on mtimes."""
    digest = hashlib.sha256()
    for path in sorted((Path(path) for path in paths), key=lambda item: item.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        if not path.is_file():
            digest.update(b"missing\0")
            continue
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def change_files_signature(changes_dir: Path) -> str:
    return files_content_signature(changes_dir.glob("changes_*.json"))


def scan_history_signature(path: Path) -> str:
    return files_content_signature((path,))
